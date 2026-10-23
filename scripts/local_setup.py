#!/usr/bin/env python3
"""Local-only Bonsai/OpenCode helpers. Python stdlib; no external deps."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

PROVIDER = "bonsai-local"


SUMMARY_MODEL = "bonsai-summary"
SUMMARY_OUTPUT_MAX = 12_288


def expected_summary_output(context: int) -> int:
    """Output headroom for compaction, independent of normal chat replies."""
    if type(context) is not int or not 8192 <= context <= 262144:
        raise ValueError("Invalid context for Bonsai summary model")
    return min(SUMMARY_OUTPUT_MAX, context // 2)


def configure_summary_model(cfg: dict) -> dict:
    """Alias the SAME PrismML GGUF with more output tokens for compaction only.

    OpenCode V2 honors agents.compaction.model. Do not change the default
    model's 4096 output cap; this avoids turning everyday answers into huge
    thinking runs. A custom compaction agent is user-owned and not replaced.
    """
    if not isinstance(cfg, dict) or cfg.get("model") != f"{PROVIDER}/bonsai":
        raise ValueError("Refusing to change non-managed Bonsai configuration")
    provider = cfg.get("providers", {}).get(PROVIDER, {})
    models = provider.get("models", {}) if isinstance(provider, dict) else {}
    base = models.get("bonsai", {}) if isinstance(models, dict) else {}
    if not isinstance(base, dict) or not isinstance(base.get("modelID"), str) or not base["modelID"]:
        raise ValueError("Bonsai modelID missing from managed config")
    limit = base.get("limit", {})
    context = limit.get("context") if isinstance(limit, dict) else None
    capacity = expected_summary_output(context)
    alias = models.get(SUMMARY_MODEL)
    if alias is not None and not isinstance(alias, dict):
        raise ValueError("Existing summary model is invalid")
    if alias is not None and alias.get("modelID") != base["modelID"]:
        raise ValueError("Summary model alias points to a different upstream model; refusing override")
    agents = cfg.setdefault("agents", {})
    if not isinstance(agents, dict):
        raise ValueError("Expected agents object in OpenCode configuration")
    compaction = agents.setdefault("compaction", {})
    if not isinstance(compaction, dict):
        raise ValueError("Expected agents.compaction object")
    configured = compaction.get("model")
    target = f"{PROVIDER}/{SUMMARY_MODEL}"
    if configured not in (None, target):
        raise ValueError("A custom compaction agent model exists; refusing to replace it")
    # Preserve non-conflicting custom agent and alias keys, but enforce
    # output/context/model identity so OpenCode cannot silently use 4096 again.
    summary = dict(alias or {})
    summary["modelID"] = base["modelID"]
    summary["name"] = "Bonsai 2 27B (compaction, larger output)"
    summary["limit"] = {"context": context, "output": capacity}
    summary["capabilities"] = base.get("capabilities", {"tools": True, "input": ["text"], "output": ["text"]})
    summary_body = summary.get("body", {})
    if not isinstance(summary_body, dict):
        raise ValueError("Expected summary model.body object")
    # Restrict unnecessary internal deliberation for routine summaries.
    summary["body"] = {**summary_body, "reasoning_effort": "medium"}
    models[SUMMARY_MODEL] = summary
    compaction["model"] = target
    return cfg


def has_summary_model(cfg: dict) -> bool:
    """Verify that compaction cannot silently fall back to 4096 tokens."""
    try:
        base = cfg["providers"][PROVIDER]["models"]["bonsai"]
        summary = cfg["providers"][PROVIDER]["models"][SUMMARY_MODEL]
        return (
            cfg["agents"]["compaction"]["model"] == f"{PROVIDER}/{SUMMARY_MODEL}"
            and summary["modelID"] == base["modelID"]
            and summary["limit"]["context"] == base["limit"]["context"]
            and summary["limit"]["output"] == expected_summary_output(base["limit"]["context"])
            and summary["limit"]["output"] > base["limit"]["output"]
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def recommended_compaction_buffer(context: int, output: int, keep: int) -> int:
    """Reserve enough room for a useful summary, instead of truncating it.

    OpenCode V2 sizes summary output partly from the compaction buffer.
    On a 32K context, 4K buffer repeatedly truncates summaries at ~3K.
    We reserve 37.5% of context, with at least 1024 free for other input.
    """
    if any(type(v) is not int for v in (context, output, keep)):
        raise ValueError("Context/output/keep must be integers")
    room = context - output - keep - 1024
    recommended = context * 3 // 8
    if room < recommended or recommended < 4096:
        raise ValueError(
            f"Context {context} cannot safely allocate output={output}, "
            f"keep={keep} and summary buffer={recommended}; "
            "use a larger context or reduce output/keep."
        )
    return recommended


def validate_base_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Only loopback HTTP inference endpoints are accepted")
    if parts.username or parts.password or parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ValueError("Unexpected components in inference endpoint URL")
    if not parts.port or not 1 <= parts.port <= 65535:
        raise ValueError("A valid port is required")
    return value.rstrip("/")


def fetch_json(url: str, timeout: int = 8) -> dict:
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:
        return json.load(response)


def model_id(base_url: str) -> str:
    base_url = validate_base_url(base_url)
    data = fetch_json(f"{base_url}/v1/models")
    models = data.get("data", [])
    if len(models) != 1 or not isinstance(models[0].get("id"), str) or not models[0]["id"]:
        raise ValueError("Expected exactly one model with a valid ID in /v1/models")
    return models[0]["id"]


REASONING_DEFAULT = "medium"
REASONING_DEEP = "xhigh"


def apply_reasoning_profiles(cfg: dict) -> dict:
    """Set the PrismML request-body field; preserve unrelated user options.

    OpenCode V2 model.body is forwarded to OpenAI-compatible endpoints.
    V2 variants are a list whose selected body overrides the model's body.
    Bonsai 2 rejects 'high'; the deep profile must use 'xhigh'.
    """
    if not isinstance(cfg, dict) or cfg.get("model") != f"{PROVIDER}/bonsai":
        raise ValueError("Not a local-ia managed Bonsai model configuration")
    provider = cfg.get("providers", {}).get(PROVIDER, {})
    if not isinstance(provider, dict):
        raise ValueError("Invalid managed provider")
    models = provider.get("models", {})
    model = models.get("bonsai", {}) if isinstance(models, dict) else {}
    if not isinstance(model, dict) or not isinstance(model.get("modelID"), str):
        raise ValueError("Managed Bonsai model is missing its upstream model ID")
    if not isinstance(model.get("body", {}), dict):
        raise ValueError("Invalid model.body")
    variants = model.get("variants", [])
    if not isinstance(variants, list) or any(
        not isinstance(v, dict) or not isinstance(v.get("id"), str)
        for v in variants
    ):
        raise ValueError("Expected OpenCode V2 variants array")
    existing = [v for v in variants if v["id"] == "deep"]
    if len(existing) > 1:
        raise ValueError("Duplicate deep variants; resolve manually")
    selected = existing[0] if existing else {"id": "deep"}
    if not isinstance(selected.get("body", {}), dict):
        raise ValueError("Invalid deep variant body")
    model["body"] = {**model.get("body", {}), "reasoning_effort": REASONING_DEFAULT}
    selected["body"] = {**selected.get("body", {}), "reasoning_effort": REASONING_DEEP}
    if not existing:
        variants.append(selected)
    model["variants"] = variants
    return cfg


def has_reasoning_profiles(cfg: dict) -> bool:
    """True only if both explicit request-body overrides are configured."""
    try:
        model = cfg["providers"][PROVIDER]["models"]["bonsai"]
        return (
            model["body"]["reasoning_effort"] == REASONING_DEFAULT
            and any(
                v.get("id") == "deep" and
                isinstance(v.get("body"), dict) and
                v["body"].get("reasoning_effort") == REASONING_DEEP
                for v in model["variants"]
            )
        )
    except (KeyError, TypeError, AttributeError):
        return False


def configure_reasoning(path: Path | None = None) -> str:
    """Offline, additive V2 model config upgrade; leave existing sessions alone."""
    path = path or Path.home() / ".config/opencode/opencode.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Managed OpenCode config absent or symlinked: {path}; "
                         "run make configure-opencode when Bonsai is ready")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or cfg.get("model") != f"{PROVIDER}/bonsai":
        raise ValueError("Refusing to change a non-Bonsai OpenCode configuration")
    apply_reasoning_profiles(cfg)
    state = write_config(cfg, path)
    print(f"{state}: Bonsai reasoning = medium by default, deep = xhigh ({path})")
    print("No Docker restart, model reload, or session edits. Restart OpenCode to "
          "pick up configuration changes; choose deep as a variant when needed.")
    return state


def generate_config(upstream_model_id: str, context: int, output: int, keep: int, buffer: int, base_url: str) -> dict:
    validate_base_url(base_url)
    if not upstream_model_id or not isinstance(upstream_model_id, str):
        raise ValueError("Invalid upstream model ID")
    if not (8192 <= context <= 262144):
        raise ValueError("Context must be between 8192 and 262144")
    if not (1 <= output < context):
        raise ValueError("Output budget must be positive and smaller than context")
    if keep < 0 or buffer < 0 or keep + buffer + output >= context:
        raise ValueError("Compaction keep + buffer + output must leave input room")
    minimum_buffer = recommended_compaction_buffer(context, output, keep)
    if buffer < minimum_buffer:
        raise ValueError(
            f"Compaction buffer {buffer} is too small for {context} context; "
            f"use OPENCODE_BUFFER={minimum_buffer} or larger."
        )
    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "model": f"{PROVIDER}/bonsai",
        "providers": {
            PROVIDER: {
                "name": "Bonsai Local (PrismML)",
                "package": "@opencode/ai/providers/openai-compatible",
                "settings": {"baseURL": f"{base_url}/v1"},
                "models": {
                    "bonsai": {
                        "modelID": upstream_model_id,
                        "name": "Bonsai 2 27B PQ2_0 (Local)",
                        "limit": {"context": context, "output": output},
                        "capabilities": {"tools": True, "input": ["text"], "output": ["text"]},
                    }
                },
            }
        },
        "compaction": {"auto": True, "keep": {"tokens": keep}, "buffer": buffer},
        "policies": [
            {"action": "provider.use", "resource": "*", "effect": "deny"},
            {"action": "provider.use", "resource": PROVIDER, "effect": "allow"},
        ],
        "permissions": [
            {"action": "shell", "resource": "*", "effect": "ask"},
            {"action": "shell", "resource": "git status *", "effect": "allow"},
            {"action": "shell", "resource": "git diff *", "effect": "allow"},
            {"action": "shell", "resource": "git push *", "effect": "deny"},
            {"action": "edit", "resource": "*", "effect": "ask"},
            {"action": "external_directory", "resource": "*", "effect": "ask"},
            {"action": "read", "resource": "*.env", "effect": "ask"},
            {"action": "read", "resource": "*.env.*", "effect": "ask"},
            {"action": "read", "resource": "*.env.example", "effect": "allow"},
        ],
    }
    return configure_summary_model(apply_reasoning_profiles(cfg))


def write_config(config: dict, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_content = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == new_content:
            return "Unchanged"
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        target = path.with_name(f"{path.name}.bak-{stamp}-{time.time_ns() % 1_000_000:06d}")
        shutil.copy2(path, target)
        target.chmod(0o600)
        print(f"Previous OpenCode configuration backed up at {target}")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".opencode-", delete=False) as fp:
        fp.write(new_content)
        tmp = Path(fp.name)
    try:
        tmp.chmod(0o600)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return "Written"


OPENCODE_V2_VERSION = re.compile(
    r"(?:opencode\s+)?v?2\.\d+\.\d+(?:[-+][a-z0-9.-]+)?",
    flags=re.IGNORECASE,
)


def valid_opencode_v2_version(output: str) -> bool:
    """Parse official CLI output, including 'opencode v2.1.3'."""
    return bool(OPENCODE_V2_VERSION.fullmatch(output.strip()))


def fix_compaction(path: Path | None = None) -> str:
    """Offline fix for both OpenCode compaction trigger and output token budget.

    Makes one private backup if changes are needed. Does not touch sessions,
    Docker, model weights, or ordinary chat output limit.
    """
    path = path or Path.home() / ".config/opencode/opencode.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            f"OpenCode config missing, invalid or symlinked: {path}; "
            "configure it with make configure-opencode when Bonsai is ready."
        )
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or cfg.get("model") != f"{PROVIDER}/bonsai":
        raise ValueError("Refusing to modify a config that is not the managed Bonsai model")
    comp = cfg.get("compaction")
    if not isinstance(comp, dict):
        raise ValueError("Managed OpenCode config has no compaction settings")
    limits = cfg.get("providers", {}).get(PROVIDER, {}).get("models", {}).get("bonsai", {}).get("limit", {})
    keep_obj = comp.get("keep", {})
    keep = keep_obj.get("tokens") if isinstance(keep_obj, dict) else None
    context, output, buffer = limits.get("context"), limits.get("output"), comp.get("buffer")
    if type(buffer) is not int or buffer < 0:
        raise ValueError("Invalid existing compaction.buffer")
    required = recommended_compaction_buffer(context, output, keep)
    old_buffer = buffer
    if buffer < required:
        cfg["compaction"]["buffer"] = required
    configure_summary_model(cfg)
    state = write_config(cfg, path)
    if state == "Written":
        print(f"Fixed compaction buffer: {old_buffer} -> {cfg['compaction']['buffer']}")
        print(f"Compaction-only model output: {cfg['providers'][PROVIDER]['models'][SUMMARY_MODEL]['limit']['output']} tokens")
        print(f"Everyday Bonsai output remains: {output} tokens")
        print(f"Private config backup created; original sessions remain untouched.")
    else:
        print("Compaction buffer and dedicated summary output model already configured.")
    print("Restart OpenCode to load the repaired summary model; no Docker restart.")
    print("If the old session still cannot compact, preserve/export it and start a new session.")
    return state


def opencode_v2_installed() -> bool:
    cmd = shutil.which("opencode")
    if not cmd:
        return False
    try:
        result = subprocess.run([cmd, "--version"], capture_output=True,
                                text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and valid_opencode_v2_version(result.stdout)


def check_server_context(base_url: str, requested: int) -> None:
    try:
        props = fetch_json(f"{base_url}/props", timeout=3)
        # llama.cpp versions vary; report only when a numeric value is exposed.
        settings = props.get("default_generation_settings", {})
        actual = settings.get("n_ctx") if isinstance(settings, dict) else None
        if isinstance(actual, int) and actual > 0 and requested > actual:
            raise ValueError(f"OpenCode would announce {requested} tokens, but /props reports only {actual}")
        if isinstance(actual, int) and actual > 0:
            print(f"llama-server context reported by /props: {actual}")
        else:
            print("INFO: /props does not report a comparable context value; verify n_ctx_slot in server log.")
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError, KeyError):
        print("INFO: Could not verify context through /props; inspect server n_ctx_slot before agent use.")


def configure(base: str, context: int, output: int, keep: int, buffer: int, path: Path | None = None) -> dict:
    if not opencode_v2_installed():
        raise RuntimeError("OpenCode V2 is not in PATH; install V2 or refresh your shell first")
    upstream = model_id(base)
    check_server_context(base, context)
    cfg = generate_config(upstream, context, output, keep, buffer, base)
    path = path or Path.home() / ".config/opencode/opencode.json"
    state = write_config(cfg, path)
    print(f"{state}: {path}\nModel ID: {upstream}\nProvider policy: {PROVIDER} only")
    return cfg



def wait_until_ready(base: str, timeout: float = 120.0, interval: float = 2.0,
                     clock=None, sleeper=None) -> str:
    """Wait until the *model* is ready; process startup alone is insufficient.

    A 200 response with `status=loading` is not ready. Query model metadata only
    once the health endpoint returns ready. Retry transient HTTP and JSON errors.
    """
    base = validate_base_url(base)
    if not 0 < timeout <= 3600 or not 0 < interval <= 60:
        raise ValueError("Ready timeout/interval out of range")
    clock = clock or time.monotonic
    sleeper = sleeper or time.sleep
    deadline = clock() + timeout
    last = "server not ready"
    while True:
        try:
            info = fetch_json(f"{base}/health", timeout=5)
            if info.get("status") == "ok":
                current = model_id(base)
                print(f"READY: {current} at {base}")
                return current
            last = f"/health status={info.get('status', 'unknown')}"
        except (OSError, ValueError, TypeError, KeyError) as exc:
            last = str(exc)
        remaining = deadline - clock()
        if remaining <= 0:
            raise RuntimeError(f"Bonsai not ready after {timeout:g}s: {last}")
        sleeper(min(interval, remaining))


def gpu_info() -> None:
    nvidia = shutil.which("nvidia-smi")
    if not nvidia:
        print("NVIDIA: nvidia-smi missing")
        return
    result = subprocess.run([nvidia, "--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv,noheader"], capture_output=True, text=True, timeout=8, check=False)
    print("GPU compute processes:\n" + (result.stdout.strip() or "(none reported)"))


def status(base: str) -> None:
    validate_base_url(base)
    try:
        health = fetch_json(f"{base}/health", timeout=4)
        print(f"llama-server: {health}")
        print(f"Models: {', '.join(m['id'] for m in fetch_json(base + '/v1/models').get('data', []))}")
    except (OSError, ValueError, KeyError) as error:
        print(f"llama-server: UNAVAILABLE ({error})")
    gpu_info()


def doctor(base: str, demo_dir: Path, context: int) -> None:
    print(f"Bonsai demo: {demo_dir}")
    print(f"Requested context: {context}")
    if not (demo_dir / "scripts/start_llama_server.sh").exists():
        print("Bonsai: MISSING. Run make install-bonsai")
    ggufs = list((demo_dir / "models/bonsai2-gguf/27B").glob("*PQ2_0.gguf"))
    print(f"Model weights: {'OK' if ggufs else 'MISSING'}")
    site_paths = list((demo_dir / ".venv").glob("lib/python*/site-packages/nvidia"))
    for libpath in ["cuda_runtime/lib/libcudart.so.12", "cublas/lib/libcublas.so.12", "cublas/lib/libcublasLt.so.12"]:
        print(f"{libpath}: {'OK' if any((site / libpath).exists() for site in site_paths) else 'MISSING'}")
    print(f"OpenCode V2: {'OK' if opencode_v2_installed() else 'MISSING'}")
    if (demo_dir / "bin/cuda/llama-server").exists():
        print("CUDA llama-server binary: OK (dynamic dependency check happens in make server)")
    status(base)


def completion(base: str, max_tokens: int) -> None:
    validate_base_url(base)
    upstream = model_id(base)
    prompt = "Responde brevemente: ¿cuánto es 2 + 2?"
    payload = json.dumps({"model": upstream, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "stream": False}).encode("utf-8")
    req = Request(f"{base}/v1/chat/completions", data=payload, headers={"Content-Type": "application/json"})
    begin = time.monotonic()
    with urlopen(req, timeout=180) as resp:
        data = json.load(resp)
    elapsed = time.monotonic() - begin
    usage = data.get("usage", {})
    generated = usage.get("completion_tokens")
    print(f"Elapsed: {elapsed:.2f}s")
    if isinstance(generated, int) and elapsed:
        print(f"Completion tokens: {generated}, wall-clock average: {generated / elapsed:.2f} tok/s (includes prefill)")
    for choice in data.get("choices", []):
        print("Content:", (choice.get("message") or {}).get("content", ""))
    if not data.get("choices"):
        raise ValueError("No choices received from local inference endpoint")


def main(argv: list[str]) -> None:
    if not argv:
        raise SystemExit("Usage: local_setup.py {configure|configure-reasoning|doctor|status|completion|check-opencode|fix-compaction|ready} ...")
    cmd = argv[0]
    if cmd == "configure-reasoning" and len(argv) == 1:
        configure_reasoning()
    elif cmd == "fix-compaction" and len(argv) == 1:
        fix_compaction()
    elif cmd == "check-opencode" and len(argv) == 1:
        if not opencode_v2_installed():
            raise RuntimeError("OpenCode V2 missing or unsupported version; check 'opencode --version' and PATH")
        print("OpenCode V2: OK")
    elif cmd == "configure" and len(argv) == 6:
        configure(validate_base_url(argv[1]), *map(int, argv[2:]))
    elif cmd == "doctor" and len(argv) == 4:
        doctor(validate_base_url(argv[1]), Path(argv[2]).expanduser(), int(argv[3]))
    elif cmd == "status" and len(argv) == 2:
        status(validate_base_url(argv[1]))
    elif cmd == "completion" and len(argv) == 3:
        completion(validate_base_url(argv[1]), int(argv[2]))
    elif cmd == "ready" and len(argv) == 3:
        wait_until_ready(validate_base_url(argv[1]), float(argv[2]))
    else:
        raise SystemExit(f"Unknown command/args: {cmd}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (ValueError, RuntimeError, URLError, HTTPError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

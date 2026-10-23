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
    return {
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
        raise SystemExit("Usage: local_setup.py {configure|doctor|status|completion|check-opencode|ready} ...")
    cmd = argv[0]
    if cmd == "check-opencode" and len(argv) == 1:
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

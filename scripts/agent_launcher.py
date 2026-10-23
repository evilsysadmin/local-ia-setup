#!/usr/bin/env python3
"""OpenCode launcher with local-provider checks and conservative Git gates.

Plan is for analysis. Build requires an explicitly clean feature branch.
This is a workflow safeguard, not a sandbox against agent/command execution.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import local_setup
import compose_lifecycle

MODEL = "bonsai-local/bonsai"
PROTECTED = frozenset({"main", "master", "trunk", "production"})
OVERRIDES = ("OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT", "OPENCODE_CONFIG_DIR")


def git(*args: str, cwd: Path, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, check=check, timeout=15,
    )
    return result.stdout.strip()


def resolve_project(raw: str | None) -> Path:
    if not raw:
        raise ValueError("Missing PROJECT. Example: make agent PROJECT=~/Documents/repos/evilsysadmin/chess-studio")
    path = Path(raw).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise ValueError(f"PROJECT is not a directory: {path}")
    if git("rev-parse", "--is-inside-work-tree", cwd=path, check=False) != "true":
        raise ValueError(f"PROJECT must be inside a Git worktree: {path}")
    return Path(git("rev-parse", "--show-toplevel", cwd=path)).resolve(strict=True)


def validate_config(path: Path, upstream_id: str, base_url: str, requested_ctx: int,
                    require_deep: bool = False) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"OpenCode config missing or is a symlink: {path}; run make configure-opencode")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("model") != MODEL:
        raise ValueError("OpenCode default model is not bonsai-local/bonsai; run make configure-opencode")
    provider = cfg.get("providers", {}).get("bonsai-local", {})
    model = provider.get("models", {}).get("bonsai", {})
    if provider.get("settings", {}).get("baseURL") != f"{base_url}/v1":
        raise ValueError("Configured local API URL differs from running Bonsai")
    if model.get("modelID") != upstream_id:
        raise ValueError("Configured model ID differs from running Bonsai; run make configure-opencode")
    if model.get("limit", {}).get("context") != requested_ctx:
        raise ValueError("Configured context differs from BONSAI_CTX; run make configure-opencode")
    rules = cfg.get("policies", [])
    required = [
        {"action": "provider.use", "resource": "*", "effect": "deny"},
        {"action": "provider.use", "resource": "bonsai-local", "effect": "allow"},
    ]
    if not isinstance(rules, list) or not all(rule in rules for rule in required):
        raise ValueError("Managed local-only provider policy missing; run make configure-opencode")
    if require_deep and not local_setup.has_reasoning_profiles(cfg):
        raise ValueError("Bonsai deep variant missing; run make configure-reasoning first")


def check_worktree(root: Path, mode: str) -> tuple[str, int]:
    branch = git("symbolic-ref", "-q", "--short", "HEAD", cwd=root, check=False)
    if not branch:
        raise ValueError("Detached HEAD: create or check out a named branch")
    changes = git("status", "--porcelain=v1", "--untracked-files=normal", cwd=root)
    dirty = len(changes.splitlines()) if changes else 0
    if mode == "build":
        if branch in PROTECTED:
            raise ValueError(f"Build refused on '{branch}': use a feature branch or Git worktree")
        if dirty:
            raise ValueError(f"Build refused: {dirty} pending change(s); commit/stash or use a clean worktree")
    return branch, dirty


def preflight(project: str | None, mode: str, base_url: str, ctx: int,
              config: Path | None = None, require_deep: bool = False) -> Path:
    if mode not in {"plan", "build"}:
        raise ValueError("Mode must be 'plan' or 'build'")
    for name in OVERRIDES:
        if os.environ.get(name):
            raise ValueError(f"{name} would override managed config; unset before using this launcher")
    root = resolve_project(project)
    branch, dirty = check_worktree(root, mode)
    base = local_setup.validate_base_url(base_url)
    upstream = local_setup.wait_until_ready(base, timeout=12, interval=1)
    path = config or Path.home() / ".config/opencode/opencode.json"
    validate_config(path, upstream, base, ctx, require_deep=require_deep)
    local_setup.check_server_context(base, ctx)
    if not shutil.which("opencode") or not local_setup.opencode_v2_installed():
        raise RuntimeError("OpenCode V2 not in PATH; run make install-opencode")
    print(f"PROJECT: {root}", flush=True)
    print(f"BRANCH: {branch} ({dirty} pending change(s))", flush=True)
    print(f"AGENTS.md: {'present' if (root / 'AGENTS.md').is_file() else 'not found'}", flush=True)
    if (root / "opencode.json").exists() or (root / "opencode.jsonc").exists():
        print("WARNING: project OpenCode config may override global provider and permissions", flush=True)
    if (root / ".opencode").exists():
        print("WARNING: project .opencode/ may add agents/plugins/config overrides", flush=True)
    print(f"AGENT: {mode}; MODEL: {MODEL}", flush=True)
    print("OpenCode tools retain your user permissions; this launcher is not a security sandbox.", flush=True)
    return root


def main(argv: list[str]) -> None:
    if len(argv) not in {3, 4}:
        raise ValueError("Usage: agent_launcher.py {plan|build} LOCAL_URL CONTEXT [deep]; set PROJECT")
    mode, url, context = argv[:3]
    variant = argv[3] if len(argv) == 4 else None
    if variant not in {None, "deep"}:
        raise ValueError("Only the explicit 'deep' variant is supported")
    # Validate request and OpenCode availability before loading a large model.
    project = os.environ.get("PROJECT")
    root = resolve_project(project)
    check_worktree(root, mode)
    if variant == "deep":
        config_path = Path.home() / ".config/opencode/opencode.json"
        if config_path.is_symlink() or not config_path.is_file():
            raise ValueError("Bonsai config missing; run make configure-opencode")
        if not local_setup.has_reasoning_profiles(json.loads(config_path.read_text(encoding="utf-8"))):
            raise ValueError("Deep variant not configured; run make configure-reasoning")
    if not local_setup.opencode_v2_installed():
        raise RuntimeError("OpenCode V2 not found. Check PATH/version or run make install-opencode")
    compose_lifecycle.up(url, int(context), float(os.environ.get("BONSAI_READY_TIMEOUT", "120")),
                 Path(os.environ.get("BONSAI_DIR", str(Path.home() / "Apps/Bonsai-demo"))))
    root = preflight(project, mode, url, int(context), require_deep=(variant == "deep"))
    os.chdir(root)
    selection = MODEL + ("#deep" if variant == "deep" else "")
    print(f"REASONING: {'xhigh (deep)' if variant == 'deep' else 'medium (default)'}",
          flush=True)
    os.execvp("opencode", ["opencode", "--model", selection, "--agent", mode])


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

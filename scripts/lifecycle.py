#!/usr/bin/env python3
"""Opt-in lifecycle for LOCAL Bonsai without touching foreign processes.

'make up' may install/start our user-scoped unit; it never enables login
autostart, installs drivers, deletes state, kills processes or takes over a port.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import local_setup
import user_service


def listener_present(base: str) -> bool:
    target = urlsplit(local_setup.validate_base_url(base))
    try:
        with socket.create_connection((target.hostname, target.port), timeout=0.4):
            return True
    except OSError:
        return False


def managed_active() -> bool:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", user_service.NAME],
        capture_output=True, check=False, timeout=10,
    )
    return result.returncode == 0


def matching_bonsai_pids(binary: Path) -> list[int]:
    """Find the exact CUDA server executable via Linux /proc, without signalling."""
    found = []
    if not binary.is_file() or not Path("/proc").is_dir():
        return found
    try:
        real_binary = binary.resolve()
    except OSError:
        return found
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal() or int(proc.name) == os.getpid():
            continue
        try:
            if (proc / "exe").resolve(strict=True) == real_binary:
                found.append(int(proc.name))
        except (OSError, PermissionError):
            continue
    return sorted(found)


def verify_ready(base: str, context: int, timeout: float) -> str:
    current = local_setup.wait_until_ready(base, timeout=timeout, interval=2)
    if "bonsai" not in current.casefold():
        raise RuntimeError(
            f"Local port is serving an unexpected model ({current!r}); "
            "refusing to treat this as Bonsai. Stop the other server explicitly."
        )
    local_setup.check_server_context(base, context)
    return current


def up(base: str, context: int, timeout: float, demo_dir: Path) -> str:
    base = local_setup.validate_base_url(base)
    if not 0 < timeout <= 3600:
        raise ValueError("BONSAI_READY_TIMEOUT must be between 1 and 3600 seconds")
    if not 8192 <= context <= 262144:
        raise ValueError("Invalid context size")

    if listener_present(base):
        model = verify_ready(base, context, timeout)
        print(f"REUSED: existing healthy local server ({model}); did not start another.", flush=True)
        return "reused"

    # A managed service can be starting before it binds its HTTP port.
    if managed_active():
        verify_ready(base, context, timeout)
        print("REUSED: local-ia-bonsai.service was already running.", flush=True)
        return "managed"

    # A lingering CUDA process can hold VRAM without answering on localhost.
    # Do not start a second 8+ GiB model, and especially do not kill it.
    pids = matching_bonsai_pids(demo_dir / "bin/cuda/llama-server")
    if pids:
        raise RuntimeError(
            f"Detected the existing Bonsai llama-server PID(s) {pids}, but "
            f"{base} is not listening and the managed unit is not active. "
            "Refusing to start another model or kill those processes. "
            "Inspect with ps -fp PID / ss -ltnp; stop the old process yourself."
        )

    repo = Path(__file__).resolve().parent.parent
    result = user_service.install(repo)
    print(f"User service: {result} (login autostart unchanged).", flush=True)
    try:
        user_service.systemctl("start", user_service.NAME)
        verify_ready(base, context, timeout)
        if not managed_active():
            raise RuntimeError("Managed unit exited unexpectedly after startup")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"Managed Bonsai startup failed: {exc}. Inspect make service-logs.") from exc
    print("STARTED: managed Bonsai server is ready.", flush=True)
    return "started"


def down(base: str) -> str:
    base = local_setup.validate_base_url(base)
    path = user_service.service_path()
    if not user_service.check_ours(path):
        print("No local-ia managed service installed: nothing stopped.", flush=True)
        return "not-installed"
    if not managed_active():
        print("Managed service is already stopped; no other processes touched.", flush=True)
        return "stopped"
    user_service.systemctl("stop", user_service.NAME)
    print("STOPPED: managed user service. Foreign/manual servers were not touched.", flush=True)
    if listener_present(base):
        print(f"NOTICE: something still listens at {base}; inspect it separately.", flush=True)
    return "stopped"


def main(argv: list[str]) -> None:
    if len(argv) != 5:
        raise ValueError("Usage: lifecycle.py {up|down} URL CONTEXT TIMEOUT BONSAI_DIR")
    action, base, context, timeout, demo_dir = argv
    if action == "up":
        up(base, int(context), float(timeout), Path(demo_dir).expanduser())
    elif action == "down":
        down(base)
    else:
        raise ValueError(f"Unknown lifecycle action: {action}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

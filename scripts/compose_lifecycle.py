#!/usr/bin/env python3
"""Container lifecycle for the PrismML-fork llama-server.

Model, CUDA binary and upstream launcher stay in the user's existing
Bonsai-demo checkout; Compose mounts it read-only. Never kill foreign PIDs.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import lifecycle
import local_setup

PROJECT = "local-ia-bonsai"
SERVICE = "bonsai"
LABEL = "io.github.evilsysadmin.local-ia-setup.component"
LABEL_VALUE = "bonsai-prisml"
COMPOSE = Path(__file__).resolve().parent.parent / "docker" / "compose.yaml"


def call(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                            check=False)
    if result.returncode:
        raise RuntimeError(f"{' '.join(args[:4])} failed: "
                           f"{(result.stderr or result.stdout).strip()[:700]}")
    return result.stdout.strip()


def compose(*args: str, timeout: int = 30) -> str:
    return call(["docker", "compose", "-p", PROJECT, "-f", str(COMPOSE),
                 *args], timeout=timeout)


def docker_available() -> None:
    if not shutil.which("docker"):
        raise RuntimeError("Docker missing. Install Docker Engine + Compose plugin "
                           "or use make native-up (systemd --user).")
    try:
        call(["docker", "compose", "version"], timeout=10)
        call(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=10)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Docker Compose/daemon unavailable: {exc}. "
                           "Also install NVIDIA Container Toolkit for GPU access.") from exc


def existing_container(demo_dir: Path) -> str | None:
    ids = compose("ps", "-a", "-q", SERVICE).splitlines()
    if not ids:
        return None
    if len(ids) != 1:
        raise RuntimeError("Several containers share our Compose service. "
                           "Refusing to operate on ambiguous state.")
    info = json.loads(call(["docker", "inspect", ids[0]]))
    if len(info) != 1:
        raise RuntimeError("Invalid Docker inspect response")
    obj = info[0]
    labels = obj.get("Config", {}).get("Labels", {}) or {}
    mounts = obj.get("Mounts", []) or []
    valid = (
        labels.get("com.docker.compose.project") == PROJECT
        and labels.get("com.docker.compose.service") == SERVICE
        and labels.get(LABEL) == LABEL_VALUE
        and any(m.get("Destination") == "/bonsai"
                and Path(m.get("Source", "/nonexistent")).resolve() == demo_dir.resolve()
                and not m.get("RW", True) for m in mounts)
    )
    if not valid:
        raise RuntimeError("Compose project name is occupied by a container "
                           "without our expected label and read-only Bonsai mount. "
                           "Refusing to take it over.")
    return ids[0]


def check_demo(demo_dir: Path) -> None:
    if not (demo_dir / "scripts/start_llama_server.sh").is_file():
        raise RuntimeError("PrismML launch script missing. Check BONSAI_DIR.")
    if not (demo_dir / "bin/cuda/llama-server").is_file():
        raise RuntimeError("PrismML CUDA llama-server missing. Check BONSAI_DIR.")
    if not list((demo_dir / "models/bonsai2-gguf/27B").glob("*PQ2_0.gguf")):
        raise RuntimeError("Bonsai 2 27B PQ2_0 weights missing; "
                           "this Compose will not download models.")


def up(base: str, context: int, timeout: float, demo_dir: Path) -> str:
    base = local_setup.validate_base_url(base)
    demo_dir = demo_dir.expanduser().resolve()
    if not 0 < timeout <= 3600 or not 8192 <= context <= 262144:
        raise ValueError("Invalid readiness timeout or model context")

    # Reuse a healthy local Bonsai without assuming Docker owns it.
    if lifecycle.listener_present(base):
        lifecycle.verify_ready(base, context, timeout)
        print("REUSED: already healthy Bonsai server; no new container.", flush=True)
        return "reused"

    # Keep an existing native service and orphan GPU processes untouched.
    if lifecycle.managed_active():
        lifecycle.verify_ready(base, context, timeout)
        print("REUSED: existing native systemd service; no container started.", flush=True)
        return "native"

    docker_available()
    container = existing_container(demo_dir)
    if not container:
        pids = lifecycle.matching_bonsai_pids(demo_dir / "bin/cuda/llama-server")
        if pids:
            raise RuntimeError(
                f"Existing PrismML llama-server PID(s) {pids} without API at {base}. "
                "No container started. Inspect ps/ss/logs, then stop the old "
                "process explicitly; this repository never kills foreign PIDs.")
    check_demo(demo_dir)
    try:
        compose("up", "-d", "--build", "--no-deps", SERVICE, timeout=600)
        if not existing_container(demo_dir):
            raise RuntimeError("Compose created no identifiable Bonsai container")
        lifecycle.verify_ready(base, context, timeout)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"PrismML Compose startup failed: {exc}. "
                           "Inspect with make compose-logs and docker compose ps. "
                           "Do not start a second GPU server.") from exc
    print("READY: PrismML llama-server is managed by Docker Compose.", flush=True)
    return "started"


def down(base: str, demo_dir: Path) -> str:
    local_setup.validate_base_url(base)
    docker_available()
    if not existing_container(demo_dir.expanduser().resolve()):
        print("No owned Compose container to stop; no native/manual processes touched.")
        return "absent"
    compose("down", "--timeout", "40", timeout=90)
    print("STOPPED: only this project's Compose stack; host models remain untouched.")
    return "stopped"


def logs(demo_dir: Path) -> None:
    docker_available()
    if not existing_container(demo_dir.expanduser().resolve()):
        print("No owned Compose container; no logs.")
        return
    print(compose("logs", "--tail", "100", SERVICE))


def main(argv: list[str]) -> None:
    if len(argv) != 5:
        raise ValueError("Usage: compose_lifecycle.py {up|down|logs} URL CTX TIMEOUT BONSAI_DIR")
    command, base, context, timeout, demo = argv
    demo_dir = Path(demo)
    if command == "up":
        up(base, int(context), float(timeout), demo_dir)
    elif command == "down":
        down(base, demo_dir)
    elif command == "logs":
        logs(demo_dir)
    else:
        raise ValueError(f"Unknown command: {command}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

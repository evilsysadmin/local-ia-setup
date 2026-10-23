#!/usr/bin/env python3
"""Optional, non-root systemd user service for the existing Bonsai installation."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

NAME = "local-ia-bonsai.service"
MARKER = "# Managed by local-ia-setup; do not edit by hand."


def quote_unit_arg(value: str) -> str:
    """Quote one systemd command argument and escape specifiers."""
    if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid path for systemd unit")
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def render_unit(repo: Path) -> str:
    repo = repo.resolve(strict=True)
    runner = repo / "scripts" / "local-ia"
    if not runner.is_file():
        raise FileNotFoundError(f"Missing launcher: {runner}")
    return f"""{MARKER}
[Unit]
Description=Local Bonsai 2 inference server (PrismML/CUDA)
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=exec
ExecStart=/usr/bin/bash {quote_unit_arg(str(runner))} server
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGINT
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=default.target
"""


def service_path(config_home: Path | None = None) -> Path:
    if config_home is None:
        config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config_home.expanduser() / "systemd" / "user" / NAME


def check_ours(path: Path) -> bool:
    if path.is_symlink():
        raise RuntimeError(f"Refusing to modify symlink: {path}")
    if not path.exists():
        return False
    if not path.is_file() or not path.read_text(encoding="utf-8").startswith(MARKER + "\n"):
        raise RuntimeError(f"Refusing to replace unmanaged unit: {path}")
    return True


def systemctl(*args: str) -> None:
    subprocess.run(["systemctl", "--user", *args], check=True)


def install(repo: Path, path: Path | None = None) -> str:
    target = path or service_path()
    rendered = render_unit(repo)
    exists = check_ours(target)
    if exists and target.read_text(encoding="utf-8") == rendered:
        return "Unchanged"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, prefix=".local-ia-", delete=False) as f:
        f.write(rendered)
        tmp = Path(f.name)
    try:
        tmp.chmod(0o644)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    systemctl("daemon-reload")
    return "Updated" if exists else "Installed"


def uninstall(path: Path | None = None) -> str:
    target = path or service_path()
    if not check_ours(target):
        return "Not installed"
    # Stop and disable BEFORE deleting the unit, including any autostart symlinks.
    systemctl("disable", "--now", NAME)
    target.unlink()
    systemctl("daemon-reload")
    return "Uninstalled"


def main(argv: list[str]) -> None:
    action = argv[0] if len(argv) == 1 else ""
    if action == "install":
        repo = Path(__file__).resolve().parent.parent
        print(f"{install(repo)}: {service_path()} (not enabled or started)")
    elif action == "uninstall":
        print(uninstall())
    elif action == "start":
        if not check_ours(service_path()):
            raise RuntimeError("Service not installed: run make service-install")
        systemctl("start", NAME)
    elif action == "stop":
        systemctl("stop", NAME)
    elif action == "restart":
        systemctl("restart", NAME)
    elif action == "enable":
        if not check_ours(service_path()):
            raise RuntimeError("Service not installed: run make service-install")
        systemctl("enable", "--now", NAME)
    elif action == "disable":
        systemctl("disable", "--now", NAME)
    elif action == "status":
        subprocess.run(["systemctl", "--user", "status", NAME, "--no-pager"], check=False)
    elif action == "logs":
        subprocess.run(["journalctl", "--user", "-u", NAME, "-n", "100", "--no-pager"], check=True)
    else:
        raise ValueError("Usage: user_service.py {install|uninstall|start|stop|restart|enable|disable|status|logs}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

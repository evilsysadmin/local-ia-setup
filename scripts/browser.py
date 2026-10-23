#!/usr/bin/env python3
"""Open PrismML's LOCAL llama-server Web UI in the desktop's default browser."""
from __future__ import annotations

import shutil
import subprocess
import sys

import local_setup


def open_browser(base: str) -> str:
    base = local_setup.validate_base_url(base)
    try:
        model = local_setup.wait_until_ready(base, timeout=5, interval=1)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeError(
            f"No ready Bonsai model at {base}. Run 'make up' first "
            f"and inspect 'make compose-logs' if startup fails. Details: {exc}"
        ) from exc
    if "bonsai" not in model.casefold():
        raise RuntimeError(
            f"The local API reports {model!r}, not Bonsai; refusing to open an "
            "unrelated service."
        )

    if shutil.which("xdg-open"):
        args = ["xdg-open", base]
    elif shutil.which("gio"):
        args = ["gio", "open", base]
    else:
        raise RuntimeError(
            "No desktop URL opener (xdg-open/gio) found. "
            f"Open {base} manually in your browser."
        )
    try:
        subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError as exc:
        raise RuntimeError(f"Browser launch failed: {exc}; open {base} manually") from exc
    print(f"Opening local PrismML Web UI: {base}", flush=True)
    return base


def main(args: list[str]) -> None:
    if len(args) != 1:
        raise ValueError("Usage: browser.py http://127.0.0.1:8080")
    open_browser(args[0])


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

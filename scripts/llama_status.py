#!/usr/bin/env python3
"""Read-only llama.cpp/PrismML runtime snapshot; optional bounded Compose logs.

Does not send a completion request, start a container or read /slots prompts.
Metrics counters reset on server restart; throughput gauges are not instantaneous.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import compose_lifecycle
import local_setup

MAX_METRICS = 256 * 1024
SAMPLES = {
    "llamacpp:requests_processing": ("Requests processing", "int"),
    "llamacpp:requests_deferred": ("Requests queued", "int"),
    "llamacpp:prompt_tokens_total": ("Prompt tokens (since start)", "int"),
    "llamacpp:tokens_predicted_total": ("Generated tokens (since start)", "int"),
    "llamacpp:prompt_tokens_seconds": ("Prompt throughput (server)", "rate"),
    "llamacpp:predicted_tokens_seconds": ("Generation throughput (server)", "rate"),
    "llamacpp:kv_cache_usage_ratio": ("KV cache usage", "ratio"),
    "llamacpp:kv_cache_tokens": ("KV cache tokens", "int"),
}
SAMPLE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    r"(?:\s+\d+)?\s*$"
)


def parse_metrics(payload: str) -> dict[str, float]:
    """Parse a small, known subset of Prometheus text exposition safely."""
    parsed = {}
    for line in payload.splitlines():
        match = SAMPLE.fullmatch(line.strip())
        if not match or match[1] not in SAMPLES or match[1] in parsed:
            continue
        number = float(match[2])
        if not (number >= 0 and number < float("inf")):
            continue
        parsed[match[1]] = number
    return parsed


def get_metrics(base: str) -> tuple[dict[str, float], str | None]:
    base = local_setup.validate_base_url(base)
    try:
        req = Request(f"{base}/metrics", headers={"Accept": "text/plain"})
        with urlopen(req, timeout=4) as response:
            if response.status != 200:
                return {}, f"HTTP {response.status}"
            payload = response.read(MAX_METRICS + 1)
            if len(payload) > MAX_METRICS:
                return {}, "response exceeded 256 KiB"
        parsed = parse_metrics(payload.decode("utf-8", errors="replace"))
        if not parsed:
            return {}, "no supported llama.cpp metrics in response"
        return parsed, None
    except (HTTPError, URLError, OSError, TimeoutError, ValueError) as exc:
        if isinstance(exc, HTTPError) and exc.code in {404, 501}:
            return {}, "endpoint disabled or unsupported (restart an owned server with --metrics)"
        return {}, str(exc)


def format_metric(name: str, value: float) -> str:
    title, kind = SAMPLES[name]
    if kind == "int":
        return f"{title}: {int(value):,}"
    if kind == "ratio":
        return f"{title}: {value * 100:.1f}%"
    return f"{title}: {value:.1f} tok/s"


def get_context(base: str) -> int | None:
    try:
        data = local_setup.fetch_json(f"{base}/props", timeout=3)
        gen = data.get("default_generation_settings")
        options = [data.get("n_ctx_slot"), data.get("n_ctx")]
        if isinstance(gen, dict):
            options.append(gen.get("n_ctx"))
        for n in options:
            if isinstance(n, int) and not isinstance(n, bool) and n > 0:
                return n
    except (ValueError, OSError, TypeError):
        pass
    return None


def nvidia_memory() -> str | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total",
             "--format=csv,noheader"], capture_output=True, text=True,
            timeout=5, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def snapshot(base: str, requested_ctx: int) -> bool:
    base = local_setup.validate_base_url(base)
    print(f"PrismML llama-server  |  {base}")
    try:
        health = local_setup.fetch_json(f"{base}/health", timeout=3)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Health: OFFLINE / unreachable ({exc})")
        print("Run make up; for Docker diagnostics use make compose-ps / make compose-logs.")
        return False

    status = str(health.get("status", "unknown"))
    print(f"Health: {status}")
    if status == "ok":
        try:
            print(f"Model: {local_setup.model_id(base)}")
        except (OSError, ValueError, TypeError) as exc:
            print(f"Model: unavailable ({exc})")
    print(f"Requested context: {requested_ctx:,} tokens")
    actual = get_context(base)
    if actual is None:
        print("Server context: unavailable (/props did not expose a comparable value)")
    else:
        print(f"Server-reported context: {actual:,} tokens")
        if requested_ctx > actual:
            print("WARNING: requested context exceeds the server's reported capacity")

    metrics, error = get_metrics(base)
    if error:
        print(f"Metrics: unavailable ({error})")
    else:
        for name in SAMPLES:
            if name in metrics:
                print(format_metric(name, metrics[name]))
        print("Token totals are cumulative since server start; rates are server-reported gauges.")
        print("No inference request was generated by this status command.")

    gpu = nvidia_memory()
    if gpu:
        print("Host NVIDIA VRAM (used/total; includes other processes):")
        for line in gpu.splitlines():
            print(f"  {line}")
    return status == "ok"


def show_logs(demo_dir: Path, count: int, follow: bool) -> None:
    """Logs may contain prompts/content. Only read when explicitly requested."""
    if not count and not follow:
        return
    compose_lifecycle.docker_available()
    if not compose_lifecycle.existing_container(demo_dir.expanduser().resolve()):
        print("No owned Compose container; cannot tail its logs. "
              "For native/systemd try make service-logs.")
        return

    count = count or 30
    print(f"--- last {count} Compose log lines{' (following; Ctrl+C to exit)' if follow else ''} ---",
          flush=True)
    if not follow:
        print(compose_lifecycle.compose("logs", "--no-color", "--tail", str(count),
                                        compose_lifecycle.SERVICE, timeout=20))
        return
    args = ["docker", "compose", "-p", compose_lifecycle.PROJECT, "-f",
            str(compose_lifecycle.COMPOSE), "logs", "--follow", "--no-color",
            "--tail", str(count), compose_lifecycle.SERVICE]
    try:
        proc = subprocess.run(args, check=False)
        if proc.returncode:
            raise RuntimeError(f"Docker log follow exited with status {proc.returncode}")
    except KeyboardInterrupt:
        print("\nStopped following logs; Bonsai remains running.")


def main(argv: list[str]) -> None:
    if len(argv) != 5:
        raise ValueError("Usage: llama_status.py URL CTX BONSAI_DIR TAIL FOLLOW")
    base, ctx, directory, tail, follow = argv
    try:
        n = int(tail)
    except ValueError as exc:
        raise ValueError("TAIL must be an integer 0..1000") from exc
    if not 0 <= n <= 1000:
        raise ValueError("TAIL must be an integer 0..1000")
    if follow not in {"0", "1"}:
        raise ValueError("FOLLOW must be 0 or 1")
    # Always print the snapshot, even when the model has not loaded yet.
    snapshot(base, int(ctx))
    show_logs(Path(directory), n, follow == "1")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

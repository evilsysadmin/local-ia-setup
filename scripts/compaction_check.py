#!/usr/bin/env python3
"""Audit Bonsai compaction config and optionally a running PrismML server.

Read-only: never sends a completion, starts Docker, opens sessions, or prints
configuration secrets. This checks *our global config*, not OpenCode's
potentially merged project overrides.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import local_setup


OVERRIDES = ("OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT", "OPENCODE_CONFIG_DIR")
PROJECT_CONFIGS = (
    "opencode.json", "opencode.jsonc",
    ".opencode/opencode.json", ".opencode/opencode.jsonc",
)


def config_read(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Managed OpenCode configuration missing or symlinked; run make configure-opencode")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("OpenCode config is unexpectedly large")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError("OpenCode config must be an object")
    return cfg


def warnings_for_overrides(project: str | None) -> list[str]:
    warnings = []
    for key in OVERRIDES:
        if os.environ.get(key):
            warnings.append(f"{key} overrides the managed OpenCode configuration")
    if project:
        root = Path(project).expanduser()
        for path in PROJECT_CONFIGS:
            if (root / path).exists() or (root / path).is_symlink():
                warnings.append(f"Project has {path}; merged runtime config may differ")
    return warnings


def inspect_config(cfg: dict, endpoint: str, requested_ctx: int) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    if cfg.get("model") != "bonsai-local/bonsai":
        errors.append("Default model is not managed Bonsai")
        return errors, notes
    try:
        models = cfg["providers"]["bonsai-local"]["models"]
        normal = models["bonsai"]
        summary = models["bonsai-summary"]
        agent = cfg["agents"]["compaction"]
        comp = cfg["compaction"]
        base_url = cfg["providers"]["bonsai-local"]["settings"]["baseURL"]
        context = normal["limit"]["context"]
        normal_output = normal["limit"]["output"]
        summary_output = summary["limit"]["output"]
        keep = comp["keep"]["tokens"]
        buffer = comp["buffer"]
        if not all(type(x) is int for x in (context, normal_output, summary_output, keep, buffer)):
            raise ValueError("Token budgets must be integers")
        minimum_buffer = local_setup.recommended_compaction_buffer(context, normal_output, keep)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        errors.append(f"Invalid or incomplete compaction configuration: {exc}")
        return errors, notes

    notes.extend([
        f"Normal model: bonsai-local/bonsai ({normal_output:,} output tokens)",
        f"Compaction agent: {agent.get('model')}",
        f"Summary alias: bonsai-local/bonsai-summary ({summary_output:,} output tokens)",
        f"Context: configured {context:,}; requested {requested_ctx:,} tokens",
        f"Compaction: auto={comp.get('auto')}, keep={keep:,}, buffer={buffer:,}",
    ])
    if not local_setup.has_summary_model(cfg):
        errors.append("Compaction alias/model ID/output mismatch; run make fix-compaction")
    if buffer < minimum_buffer:
        errors.append(f"Compaction buffer too small ({buffer}); run make fix-compaction")
    if context != requested_ctx:
        errors.append("Configured context differs from BONSAI_CTX")
    if base_url != f"{endpoint}/v1":
        errors.append("Local provider API URL differs from configured BONSAI_PORT")
    if comp.get("auto") is False:
        notes.append("NOTE: automatic compaction is disabled by user preference")
    if summary.get("body", {}).get("reasoning_effort") != "medium":
        errors.append("Summary model must use medium reasoning effort")
    return errors, notes


def check_server(base: str, cfg: dict, context: int) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    try:
        health = local_setup.fetch_json(f"{base}/health", timeout=3)
    except (OSError, ValueError, TypeError) as exc:
        notes.append(f"Server: not verified ({type(exc).__name__}); static config check only")
        return problems, notes
    if health.get("status") != "ok":
        notes.append(f"Server: not ready (status={health.get('status', 'unknown')}); no inference sent")
        return problems, notes

    try:
        current_id = local_setup.model_id(base)
        configured_id = cfg["providers"]["bonsai-local"]["models"]["bonsai"]["modelID"]
        if current_id != configured_id:
            problems.append("Live PrismML model ID differs from the configured summary/normal ID")
        else:
            notes.append("Server: ready; normal and compaction aliases target its model ID")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        problems.append(f"Could not confirm live model ID: {type(exc).__name__}")

    try:
        props = local_setup.fetch_json(f"{base}/props", timeout=3)
        generation = props.get("default_generation_settings")
        candidates = [props.get("n_ctx_slot"), props.get("n_ctx")]
        if isinstance(generation, dict):
            candidates.append(generation.get("n_ctx"))
        actual = next((n for n in candidates if type(n) is int and n > 0), None)
        if actual is None:
            notes.append("Server context: not exposed by /props; inspect llama-server logs")
        elif actual < context:
            problems.append(f"Live server context {actual:,} is smaller than {context:,} configured")
        else:
            notes.append(f"Server context: {actual:,} tokens")
    except (OSError, ValueError, TypeError):
        notes.append("Server context: /props unavailable; inspect llama-server logs")
    return problems, notes


def run(base: str, ctx: int, config: Path, project: str | None = None) -> bool:
    base = local_setup.validate_base_url(base)
    cfg = config_read(config)
    errors, notes = inspect_config(cfg, base, ctx)
    overrides = warnings_for_overrides(project)
    print("Bonsai / OpenCode compaction audit (read-only)")
    for note in notes:
        print(f"  {note}")
    for note in overrides:
        print(f"WARNING: {note}")
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        server_errors, server_notes = check_server(base, cfg, ctx)
        for note in server_notes:
            print(f"  {note}")
        for error in server_errors:
            print(f"ERROR: {error}")
        errors.extend(server_errors)
    if overrides:
        print("WARNING: Global config alone cannot prove the effective merged OpenCode settings.")
        print("Inspect project overrides before relying on the compaction alias.")
    if errors:
        print("FAIL: run make fix-compaction or inspect your managed config; no files changed.")
        return False
    print("PASS: managed global compaction budgets are consistent.")
    print("No inference request generated; a live compaction still needs a real host test.")
    return True


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise ValueError("Usage: compaction_check.py LOOPBACK_URL CONTEXT")
    ok = run(
        argv[0], int(argv[1]),
        Path.home() / ".config/opencode/opencode.json",
        os.environ.get("PROJECT"),
    )
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

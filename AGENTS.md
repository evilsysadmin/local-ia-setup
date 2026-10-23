# Agent guidelines — local-ia-setup

This repo is a **reproducible local workstation setup**, not the PrismML upstream source and not a model-weights repository.

- Change one coherent concern at a time. Preserve existing local installations; never wipe model weights, Open WebUI conversations or OpenCode sessions.
- Runtime and CUDA libraries live in `~/Apps/Bonsai-demo/.venv`; do not install global NVIDIA drivers or modify `/etc/ld.so.conf*`.
- Treat `.env`, `~/.config/opencode/`, `~/.local/share/opencode/`, model files, credentials and screenshots as private. Never commit them.
- Bind APIs only to loopback; never expose the unprotected demo WebUI publicly.
- Keep OpenCode V2 JSON and PrismML llama.cpp context synchronized. Default context 32768, one slot, 4096 output and compact keep/buffer 2048/4096. Check RAM/VRAM; fall back to 16384 if needed.
- Do not hardcode the server-side model ID; request `/v1/models` before generating OpenCode config.
- Run `make verify` for every change. GPU integration tests require the actual Nobara host; never report them as passed in CI.
- `git push`, shell execution and edits by coding agents require controlled permissions; approvals do not replace isolation.
- Prefer Python standard library and Bash; keep configuration comprehensible and idempotent.
- The `systemd --user` unit is optional and manual by default: no enable, linger, sudo, or changes to global units without an explicit user command.
- The `agent` command defaults to OpenCode Plan; `agent-build` must reject protected branches and dirty worktrees. Never silently stash, reset, create branches, modify agent credentials, or autoapprove tool calls.

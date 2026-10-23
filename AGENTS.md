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
- Keep Bonsai Arena isolated in a new temporary Git repo; never write arena fixtures into a user project. Unit tests must check that changing protected tests or extra files fails the score.
- `make up` may start only the repo-managed systemd --user unit (never enable it at login), reuse a healthy Bonsai API, and must refuse orphan CUDA servers. `make down` must never signal manually started processes.
- Docker Compose is now the default `make up/down` lifecycle, launching PrismML's own CUDA server (not generic llama.cpp or Ollama), with host binaries/weights mounted read-only and API bound only to loopback. Native systemd remains optional through `make native-up/native-down`.
- `make gpu-check` must use an ephemeral non-privileged Docker NVIDIA container without mounts or host driver/daemon changes; run it before new Compose model starts, but only after guarding against orphan PrismML processes. Unit tests mock Docker so CI never claims to test real GPU access.
- `make browser` opens only a verified local Bonsai Web UI using an explicit argument-list desktop URL opener, no shell and no implicit server startup. `make chat` may call `make up` before opening the browser. Never open a remote or unrelated API URL.
- Always stream Docker Compose image pull/build logs during make up instead of buffering for minutes. `make compose-ps` must safely inspect only our owned container. A manual Docker Compose invocation must default BONSAI_DIR to the user's HOME/Apps/Bonsai-demo without relying on a shell-source of the root .env; retain read-only bind and create_host_path=false.

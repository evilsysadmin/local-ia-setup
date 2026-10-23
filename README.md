# local-ia-setup 🌳

Reproducible, **local-only** AI coding workstation for Nobara/Fedora, NVIDIA Blackwell GPU and **PrismML Bonsai 2 27B PQ2_0** with OpenCode V2 and optional Open WebUI.

**Tested live by owner in the conversation:** Nobara + MSI Vector AI HX, GeForce RTX 5070 Ti Laptop (12 GB VRAM), 32 GB RAM, NVIDIA 595.104.02, Bonsai 2 27B PQ2_0, CUDA 12 runtime. ~45–50 generated tokens/s were observed with 8K context on this machine. Those observations are **not an automated acceptance test** and should not be assumed for 32K context.

This repository contains no models, secrets, UI conversations or Nvidia drivers. It wraps the official [PrismML demo](https://github.com/PrismML-Eng/Bonsai-demo) instead of modifying its upstream scripts.

## Day-to-day use (existing installation)

Extract the provided source archive into a standalone `local-ia-setup/` directory. After publication, you can alternatively clone `https://github.com/evilsysadmin/local-ia-setup.git`.

```bash
cd local-ia-setup
cp .env.example .env                 # optional overrides
make doctor
make install-cuda                # idempotent, uv required
make server                      # terminal A; CTRL+C to stop
```

In a **second terminal**:

```bash
cd local-ia-setup
make configure-opencode           # requires the running server
cd ~/Documents/repos/evilsysadmin/chess-studio
opencode                         # use local Bonsai only
```

To start browser UI, while the backend remains running:

```bash
cd local-ia-setup
make install-webui               # only needed if not installed
make webui                      # http://127.0.0.1:9090
```

Open WebUI data remains in `~/Apps/Bonsai-demo/.openwebui`, outside this repo. Its upstream demo disables authentication; **do not expose the UI beyond localhost**.

## Clean machine bootstrap

```bash
sudo dnf install -y git curl make python3   # uv required too; install using the Nobara package manager
cp .env.example .env
make install-bonsai       # downloads PrismML fork runtime + ~8GB weights (first run only)
make install-cuda         # isolated CUDA 12 libraries in Bonsai's Python venv
make install-opencode     # official OpenCode V2 installer (inspect upstream installer)
make server
# In another terminal:
make configure-opencode
make smoke
```

`make install-bonsai` skips re-downloading if the checked-out repo contains the expected PQ2_0 model and CUDA binary. It does **not** update/overwrite upstream when it is already present. For upgrades, review changes and perform them intentionally.

## Make targets

```text
make help                List targets
make doctor              Print install/GPU/API diagnostics
make install-bonsai      Clone and set up upstream if needed
make install-cuda        Install libcudart.so.12, libcublas.so.12 and libcublasLt.so.12
make install-webui       Install Open WebUI from upstream's pinned optional dependencies
make install-opencode    Install OpenCode V2
make server              Load CUDA runpaths and launch PrismML llama-server
make configure-opencode  Build ~/.config/opencode/opencode.json from live /v1/models
make opencode            Start OpenCode (starts in the make working directory)
make webui               Launch WebUI with existing backend (won't start a second model)
make status              Show backend and active GPU compute processes
make smoke               Local API short completion
make benchmark           Wall-clock timing for a larger completion
make verify              Unit tests and syntax checks
make publish             GitHub creation (private by default, requires gh CLI)
```

## Configuration

`.env` is optional and **ignored by Git**. See `.env.example`.

| Name | Default | Why |
| --- | --- | --- |
| `BONSAI_DIR` | `~/Apps/Bonsai-demo` | Existing upstream clone (not this repo) |
| `BONSAI_CTX` | `32768` | Actual llama.cpp context; keep aligned with OpenCode |
| `BONSAI_NGL` | `99` | Request GPU offload |
| `BONSAI_SLOTS` | `1` | One local agent, no 4-way slot context split |
| `BONSAI_MMPROJ_CPU` | `1` | Save VRAM by putting vision projector in RAM |
| `BONSAI_PORT` | `8080` | Loopback API port |
| `BONSAI_OUTPUT` | `4096` | Model output allowance in OpenCode |
| `OPENCODE_KEEP` | `2048` | Recent tokens retained in compaction |
| `OPENCODE_BUFFER` | `4096` | Token buffer; avoid V2 default 16K minimum |

`BONSAI_PORT=8080` is required for the upstream Open WebUI launcher, which hardcodes port 8080. A custom port is supported by our direct server/OpenCode commands, **not** by `make webui`.

`make configure-opencode` dynamically reads the **actual** model ID from `http://127.0.0.1:8080/v1/models`, creates a single custom provider and writes V2 `policies` denying other providers. It backs up existing config and asks before shell/edit/external-directory operations. This is not a sandbox and project overrides/saved approvals warrant review.

### Troubleshooting we actually encountered

- `libcudart.so.12: not found`: install `nvidia-cuda-runtime-cu12` **in the upstream `.venv`**.
- `libcublas.so.12: not found`: also install `nvidia-cublas-cu12`; the runtime package alone isn't enough.
- `ldd llama-server` can be clean **while the CUDA backend plugin is still broken**. Inspect `libggml-cuda.so` too. Our `make server` checks both.
- `[OK] llama-server started` from upstream Open WebUI can be misleading when the backend fails; use `make doctor`/`make status` and the latest `.openwebui/logs/llama-server-*.log`.
- `Compaction request cannot be reduced...` with OpenCode V2 and 8K: OpenCode's fixed prompt/tool schemas + retention/buffer can exceed context. Prefer 32K (or 16K on VRAM pressure), then regenerate the config. New OpenCode session after changing limits.
- 12GB VRAM is finite: don't load full model plus Blender Cycles / ComfyUI at peak simultaneously.
- If `opencode` points to missing `/usr/bin/opencode` after a new install, run `hash -r` or open a fresh shell; review `type -a opencode`.

## Publishing to GitHub

The ChatGPT GitHub connector currently cannot create new repositories. On your own Nobara, after extracting this project in a standalone directory:

```bash
make verify
make publish                  # creates evilsysadmin/local-ia-setup PRIVATE by default
# or: VISIBILITY=public make publish
```

The script stages only the explicitly listed source files, initializes the repo if necessary, commits, and calls `gh repo create ... --source=. --push`. It does not add your `.env`, weights, cache or credentials. Do not run it inside another Git worktree.

This is a **reproducible setup process**, not yet a bit-for-bit locked build: the upstream PrismML demo and V2 installer may advance. For a regulated/immutable build, pin the upstream commit and CLI versions after validating them on the target GPU.

## Security and privacy

- No credentials required to download public model weights; Hugging Face tokens are optional and should never go in Git.
- Local OpenCode provider policy disables commercial providers **in the generated global config**. Inspect any separate project config and plugins.
- OpenCode executes tools under your user permissions. Use worktrees/containers for autonomous editing; verify diffs before pushing. `git push` is denied by the base configuration.
- `.env` is sourced as shell: only edit with trusted text, never paste unknown scripts into it.
- No network access is necessary for inference after installation, although installation, external tools and integrations may use it.

## Validation

`make verify` is reproducible on standard Linux CI without GPU or external API calls. A full GPU smoke test requires your actual Nobara machine, so the GitHub workflow **does not claim to validate CUDA performance**.

## Follow-up roadmap (not implemented)

- Document / RAG ingestion with strict project-level isolation; embeddings store not bundled here.
- Persistent memory strategy / backups (Open WebUI DB vs operational project memory).
- MCP + sandboxed Blender asset worker with controlled GPU scheduling.
- Optional systemd --user service, healthchecks and logs.

## References

- [PrismML demo and launcher](https://github.com/PrismML-Eng/Bonsai-demo)
- [OpenCode V2 custom providers](https://opencode.ai/v2/docs/providers)
- [OpenCode V2 compaction](https://opencode.ai/v2/docs/compaction)
- [OpenCode V2 policies](https://opencode.ai/v2/docs/policies)
- [OpenCode V2 permissions](https://opencode.ai/v2/docs/permissions)

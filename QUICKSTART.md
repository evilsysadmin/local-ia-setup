# Quickstart · local-ia-setup 🌳

Bonsai 2 27B PQ2_0 + CUDA + OpenCode V2 on **Nobara/Fedora**. Commands below run on **your own Linux machine**; this repository does **not** include model weights, credentials or conversation data.

> **Already installed Bonsai on this MSI?** Use [A](#a-bonsai-is-already-installed). You do **not** need to re-download ~8 GB of GGUF weights. For details and caveats, see [README](README.md).

## A. Bonsai is already installed

**Prerequisites:** `~/Apps/Bonsai-demo` already has the PQ2_0 model, its `.venv` and PrismML CUDA `llama-server`. Your NVIDIA driver should work (`nvidia-smi`). OpenCode V2 should be installed for the last step.

**Terminal 1 — checkout and run Bonsai** (once cloned, use `git pull --ff-only` to update):

```bash
cd ~/Documents/repos/evilsysadmin
git clone https://github.com/evilsysadmin/local-ia-setup.git
cd local-ia-setup

make doctor
make install-cuda        # safe to repeat; fixes missing libcudart/cuBLAS in Bonsai's .venv
make server              # foreground; leave this terminal open
```

**Terminal 2 — connect OpenCode:**

```bash
cd ~/Documents/repos/evilsysadmin/local-ia-setup
make ready               # wait for loaded model, not merely an open port
make configure-opencode  # reads live model ID and writes local-only V2 provider
make smoke               # optional: direct API sanity check

cd ~/Documents/repos/evilsysadmin/chess-studio
opencode                 # start in the repo you want Bonsai to inspect
```

If you previously cloned the setup repository, **do not clone again**: run `git pull --ff-only` there. If you already have a manual server on port 8080, **do not start a second**; use `make ready` and proceed to Terminal 2. To stop the foreground server, press `Ctrl+C` in Terminal 1.

`make configure-opencode` is necessary once and again after changing the context/model. It **backs up** an existing OpenCode config; it does **not** delete your sessions or credentials. OpenCode's generated provider policy allows only Bonsai local, but review any project-specific configs or plugins.

## B. New Nobara/Fedora machine

First verify the proprietary NVIDIA driver is functional: `nvidia-smi`. If not, fix that **before** installing Bonsai; these scripts do not install or alter drivers.

Install basic dependencies, including `uv` (using your distro's packaging or a trusted installer if unavailable):

```bash
sudo dnf install -y git curl make python3 uv
git clone https://github.com/evilsysadmin/local-ia-setup.git
cd local-ia-setup

make install-bonsai      # upstream setup; downloads model (~8 GB) on first run
make install-cuda        # CUDA 12 runtime + cuBLAS in Bonsai's venv, not globally
make install-opencode    # official OpenCode V2 installer; review it before running
make doctor
make server
```

Open a **new shell** if the `opencode` command is missing after installation (or run `hash -r` to clear Bash's stale command cache). In a second terminal, follow [Terminal 2 above](#a-bonsai-is-already-installed), beginning at `make ready`.

For an optional browser UI, in a third terminal after Bonsai is ready:

```bash
cd ~/Documents/repos/evilsysadmin/local-ia-setup
make install-webui       # once, if not installed
make webui               # http://127.0.0.1:9090; keep it on localhost
```

## C. Trabajar en un repositorio con el agente local

Sin cambiar de directorio, abre OpenCode apuntando a cualquier repositorio Git:

```bash
cd ~/Documents/repos/evilsysadmin/local-ia-setup
make agent PROJECT=~/Documents/repos/evilsysadmin/chess-studio
```

Esto comprueba que Bonsai está listo, el **modelo real** coincide con la
configuración de OpenCode, el contexto anunciado es coherente y se está usando
el proveedor `bonsai-local`. Abre OpenCode en la raíz del proyecto con
`--model bonsai-local/bonsai --agent plan`, adecuado para analizar código.
Permite consultar repositorios con cambios pendientes. **Plan no es un sandbox**:
sus comandos siguen sujetos a permisos y a lo que autorices.

Para permitir edición explícita, prepara una rama o worktree de trabajo limpio:

```bash
cd ~/Documents/repos/evilsysadmin/chess-studio
git switch -c bonsai/primera-prueba  # solo si esa rama aún no existe

cd ~/Documents/repos/evilsysadmin/local-ia-setup
make agent-build PROJECT=~/Documents/repos/evilsysadmin/chess-studio
```

`agent-build` rechaza ramas `main`/`master`/`trunk`/`production`,
`HEAD` separado y repositorios con archivos cambiados o sin seguimiento.
No crea ramas, no hace `stash` y nunca ejecuta `git push` automáticamente.
Estas protecciones solo se aplican **al abrir** el agente; el usuario puede
cambiar de agente o ejecutar comandos dentro de la sesión. No sustituyen
contenedores o worktrees aislados. Si el proyecto tiene sus propias
configuraciones `opencode.json` o `.opencode/`, el lanzador muestra un aviso
porque pueden modificar el comportamiento global.

## D. Prefer a background service? (optional)

Instead of leaving `make server` running, after stopping it with `Ctrl+C`:

```bash
cd ~/Documents/repos/evilsysadmin/local-ia-setup
make service-install     # installs systemd --user unit; does NOT enable autostart
make service-start       # waits for model readiness; no sudo
make service-status
make smoke
```

It will **not start at login** unless you explicitly opt in with `make service-enable`. To shut down: `make service-stop`. To disable login autostart: `make service-disable`. To remove the unit: `make service-uninstall`. Logs: `make service-logs`.

The same port is used by foreground and background modes; run **only one**. The service is user-scoped; it does not enable lingering.

## Troubleshooting (the errors we actually hit)

| Symptom | What to do |
| --- | --- |
| `libcudart.so.12` or `libcublas.so.12` missing | `make install-cuda`; do not reinstall NVIDIA drivers |
| `llama-server` answers but GPU VRAM ~200 MiB | `make doctor`; check the CUDA backend plugin with `ldd`, and `nvidia-smi` |
| `No llama backend available` in Open WebUI | Read Bonsai server logs; that message may hide a CUDA/dependency problem |
| `request (...) exceeds context` / OpenCode compaction | Make sure `BONSAI_CTX` matches the active server and re-run `make configure-opencode`; use a new OpenCode session |
| Port 8080 already bound | Reuse the running Bonsai server or stop it before switching modes |
| OpenCode not found after install | Open a new shell, run `hash -r`, then inspect `type -a opencode` |

**Operational checks:**

```bash
make ready
make status
make verify              # stdlib unit tests/syntax checks; no GPU needed
nvidia-smi               # model should consume several GiB of VRAM
```

With the confirmed MSI Vector AI HX / RTX 5070 Ti Laptop setup, Bonsai generated **~45–50 tokens/s at 8K context**; your 32K context setting still needs its own performance/VRAM measurement. The `make verify` CI job does **not** prove GPU compatibility.

**Privacy:** OpenCode tools run with your user permissions, not in a sandbox. Keep the demo API and Open WebUI on loopback, and never commit `.env`, tokens, model files, or conversations.

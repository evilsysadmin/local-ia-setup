# local-ia-setup 🌳

> **🚀 Start here:** [QUICKSTART.md](QUICKSTART.md) — Docker Compose, OpenCode, clean install, and optional native fallback.

Reproducible, **local-only** AI coding workstation for Nobara/Fedora, NVIDIA Blackwell GPU and **PrismML Bonsai 2 27B PQ2_0** with OpenCode V2 and optional Open WebUI.

**Tested live by owner in the conversation:** Nobara + MSI Vector AI HX, GeForce RTX 5070 Ti Laptop (12 GB VRAM), 32 GB RAM, NVIDIA 595.104.02, Bonsai 2 27B PQ2_0, CUDA 12 runtime. ~45–50 generated tokens/s were observed with 8K context on this machine. Those observations are **not an automated acceptance test** and should not be assumed for 32K context.

This repository contains no models, secrets, UI conversations or Nvidia drivers. It wraps the official [PrismML demo](https://github.com/PrismML-Eng/Bonsai-demo) instead of modifying its upstream scripts.

## Day-to-day use (existing installation)

Clone the [published repository](https://github.com/evilsysadmin/local-ia-setup.git) or update your checkout with `git pull --ff-only`. For the shortest setup and start/stop commands, use the [Quickstart](QUICKSTART.md).

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
make configure-reasoning  Offline upgrade: medium default and deep (xhigh) variant
make fix-compaction     Offline repair: buffer and 12K-token summary-only model (backs up config)
make compaction-check    Read-only config/server audit; PROJECT=... checks project overrides
make opencode            Start OpenCode (starts in the make working directory)
make gpu-check           Run a disposable NVIDIA CUDA container to verify GPU access
make up                  Start PrismML CUDA with Docker Compose or reuse healthy server
make browser             Open ready localhost PrismML UI in your default browser
make chat                Start/reuse Bonsai then open its local browser UI
make down                Stop only this repo's Compose container/network
make compose-logs        Tail logs from our PrismML container
make compose-ps          Inspect our Compose container without env exports
make native-up           Optional systemd --user fallback (no Docker)
make native-down         Stop only our systemd --user unit
make agent PROJECT=...    Analyze an existing Git repo using local Bonsai + Plan
make agent-build PROJECT=...  Edit in a clean feature branch with local Bonsai + Build
make agent-deep PROJECT=...   Analyze with Bonsai xhigh reasoning
make agent-build-deep PROJECT=...  Edit on a clean feature branch with xhigh
make arena               Create isolated failing-code challenge
make arena-check PROJECT=...  Evaluate five tests and detect tampering
make webui               Launch WebUI with existing backend (won't start a second model)
make status              Show backend and active GPU compute processes
make llama-status        Health, model, context, token rates/counters, requests and VRAM
make llama-status TAIL=50  Include the last 50 Compose log lines
make llama-status TAIL=50 FOLLOW=1  Follow logs live (Ctrl+C stops following)
make ready               Wait for /health=ok and valid /v1/models before returning
make smoke               Local API short completion
make benchmark           Wall-clock timing for a larger completion
make service-install     Generate optional user systemd service (no autostart)
make service-start       Start background Bonsai server; wait for model readiness
make service-stop        Stop background Bonsai server
make service-status      Show user service status
make service-logs        Show journal logs
make service-enable      Opt in to login autostart
make service-disable     Stop and disable login autostart
make service-uninstall   Safely remove generated user service
make verify              Unit tests and syntax checks
make publish             GitHub creation (private by default, requires gh CLI)
```

## Docker Compose: lanzar PrismML sin servicios systemd

Bonsai 2 requiere el **llama-server modificado de PrismML**, no Ollama
ni un llama.cpp genérico. Docker Compose ejecuta directamente el
`scripts/start_llama_server.sh` del checkout `~/Apps/Bonsai-demo`,
montado **en solo lectura** (modelos GGUF y binario CUDA incluidos).
La imagen usa `nvidia/cuda:12.8.1-runtime-ubuntu24.04` y aporta
únicamente bibliotecas y utilidades del contenedor.

Requisitos externos: Docker Engine, plugin `docker compose` y NVIDIA
Container Toolkit configurado para Docker. Verificación orientativa:

```bash
make gpu-check
```

El comando `make gpu-check` comprueba que Docker y Compose funcionan y
ejecuta `nvidia-smi` en un **contenedor efímero sin permisos privilegiados**.
Muestra GPU y VRAM; la primera vez puede descargar la imagen CUDA de prueba.
`make up` ejecuta el mismo check **antes de crear un contenedor nuevo**,
pero no lo repite al reutilizar un servidor sano ni cuando detecta un
proceso PrismML huérfano. Esta prueba no certifica que los GGUF se carguen
ni que PrismML funcione; eso lo valida después `make up`/`make smoke`.
Ninguna acción instala drivers ni modifica `daemon.json`. Consulta la
[guía oficial de NVIDIA](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
si la prueba GPU falla.

```bash
cd ~/Documents/repos/evilsysadmin/local-ia-setup
make up                  # Docker Compose + espera a que el modelo esté listo
make browser             # abre http://127.0.0.1:8080 en el navegador
make configure-opencode  # solo la primera vez o tras cambiar modelo/contexto
make agent PROJECT=~/Documents/repos/evilsysadmin/chess-studio
make compose-ps          # inspecciona el contenedor, sin exportar BONSAI_DIR
make compose-logs        # últimas 100 líneas del contenedor
make down                # para y desmonta SOLO este Compose
```

`make agent` también hace el arranque bajo demanda. El puerto del modelo
está publicado exclusivamente en `127.0.0.1`; no hay arranque automático
al iniciar sesión ni descargas nuevas del GGUF. Si existe un servidor
PrismML activo y sano, se reutiliza. Si se detecta un proceso antiguo
**sin API funcional**, el arranque se bloquea para evitar duplicar uso de
VRAM (por ejemplo, el PID 350930). Nunca se mata ese proceso: inspecciona
`ps`, `ss` y sus logs y deténlo tú si corresponde.

`make down` verifica etiquetas y montaje de solo lectura antes de apagar
el contenedor; no detiene procesos manuales ni unidades systemd. El acceso
al socket Docker da permisos elevados en el host: este Compose no es un
sandbox de OpenCode.

El primer `make up` puede necesitar descargar/construir la imagen CUDA.
La salida de Docker ahora se muestra **en directo**, para distinguir un
pull/build de un arranque bloqueado. `make compose-ps` muestra el estado
sin tener que exportar `BONSAI_DIR`; al ejecutar Compose directamente
desde otra terminal, el volumen usa `$HOME/Apps/Bonsai-demo` por defecto,
o un `BONSAI_DIR` explícito. Comprueba el checkout antes de levantar
Compose fuera del Makefile: los overrides de `.env` que carga el wrapper
no se aplican automáticamente a comandos `docker compose` directos.

**Alternativas sin Docker:** `make native-up` / `make native-down`
mantienen el servicio opcional `systemd --user`; `make server`
sigue arrancando PrismML en primer plano. No ejecutes varios modos a la vez
porque compiten por el puerto 8080 y la GPU.

Para el uso web sin OpenCode: `make chat` ejecuta `make up` y abre
el navegador predeterminado. `make browser` solo abre la UI cuando
Bonsai ya está listo, sin lanzar procesos nuevos; si no está disponible
te recomienda iniciar el servidor. Respeta `BONSAI_PORT` y localhost.

## Diagnóstico de rendimiento: llama-status

```bash
make llama-status                      # solo métricas, no genera tokens
make llama-status TAIL=50              # añade las últimas 50 líneas de Compose
make llama-status TAIL=50 FOLLOW=1     # sigue los logs en directo; Ctrl+C sale
```

Consulta únicamente endpoints localhost de lectura: `/health`,
`/v1/models`, `/props` y `/metrics`, además de `nvidia-smi` local.
Expone **peticiones activas/en cola**, tokens de prompt/generación
acumulados desde el arranque, throughput reportado de prompt/generación,
uso KV si existe y VRAM del host. Los indicadores dependen de lo que
publique esa versión del servidor; las velocidades son **gauges del
servidor**, no una prueba de rendimiento nueva ni instantánea cuando
está inactivo. No se hace petición de inferencia ni se leen los prompts
desde `/slots`. La VRAM incluye otros procesos GPU.

Los nuevos arranques de `make up` (Compose) y `make server` (nativo,
incluido `systemd --user`) pasan `--metrics` al launcher de PrismML,
compatible con llama.cpp. Si estás reutilizando un servidor anterior
que no expone `/metrics`, aparecerá `Metrics: unavailable`, sin
interrumpir el informe; reiniciar un servidor **gestionado** con el
comando apropiado habilitará las métricas, pero reiniciar borra
los contadores acumulados. Los datos se publican **solo en localhost**.
La lectura de logs es optativa porque los logs pueden contener texto
de tus peticiones; solo se consultan si indicas `TAIL` o `FOLLOW`.
Los logs corresponden exclusivamente al contenedor Compose que
pertenece a este repo (para modo nativo usa `make service-logs`).
Límites: `TAIL=0..1000`, `FOLLOW=0|1`.

## Reparar definitivamente la compactación de OpenCode V2

Si ves repetidamente `Compaction summary reached the output token limit`,
¡no sigas reenviando mensajes en la misma sesión! Observamos dos
compactaciones truncadas exactamente en **4.096 tokens de salida**,
incluso con solo 14K–15K tokens de entrada y con el buffer ya ampliado.
El problema no era solo el buffer: el modelo usado para resumir tenía
`limit.output=4096`, que OpenCode V2 también aplica al resumen.
Aumentar `compaction.buffer` adelanta la compactación, **pero no amplía**
ese techo de salida.

**Solución sin convertir todas las respuestas en monólogos:**
`make fix-compaction` actualiza la configuración OpenCode gestionada por el
repo y crea un alias `bonsai-local/bonsai-summary` que apunta al **mismo
modelo PrismML/GGUF** y al mismo localhost, pero anuncia
`limit.output=12288` en contextos de 32K.
`agents.compaction.model` selecciona este alias **solo para los resúmenes**.
El modelo conversacional `bonsai-local/bonsai` continúa con salida
máxima de 4096 tokens; el modo habitual mantiene razonamiento `medium`.

```bash
cd ~/Documents/repos/evilsysadmin/local-ia-setup
git pull --ff-only
make fix-compaction
```

Tras reparar, comprueba el contrato real **sin enviar prompts ni alterar sesiones**:

```bash
make compaction-check
make compaction-check PROJECT=~/Documents/repos/evilsysadmin/chess-studio
```

Comprueba referencias normales/de resumen, salida de 4K frente a 12K,
modelo compartido, buffer, contexto, `reasoning_effort=medium` del
resumen y `/health`, `/v1/models`, `/props` cuando el servidor está
activo. Si la API no está disponible, distingue explícitamente la
validación estática de la comprobación en vivo. No inicia Docker, no
genera inferencia y no imprime secretos ni prompts.

Con `PROJECT` avisa si existen configuraciones OpenCode locales que
podrían sobrescribir la global; estas opciones efectivas requieren
revisión manual. **Una comprobación estática correcta no garantiza**
que la compactación de una conversación larga termine bien.

La reparación es **offline, idempotente y con backup privado 0600**.
Conserva preferencias, sesiones, historial, modelo y proceso Docker.
Rechaza enlaces simbólicos, configuraciones ajenas y modelos de
compactación personalizados para no pisar decisiones del usuario.
Cierra y vuelve a abrir OpenCode para que cargue las nuevas referencias.

`make configure-opencode` ahora también genera el alias y el agente
de compactación si todavía no existe configuración. Los valores
`OPENCODE_KEEP` y `OPENCODE_BUFFER` mantienen el control de cuándo
se resume y qué contexto reciente se conserva; no deben confundirse
con el máximo de tokens del resumen.

**Recuperación de sesiones atascadas:** exporta primero la sesión con
`opencode session list` y `opencode session export SES_ID --sanitize`
(redirigiendo la salida a un archivo local privado). Tras la reparación,
prueba una vez con la sesión original. Si falla de nuevo, inicia una nueva
en el mismo repositorio; los archivos modificados y el historial guardado
continúan intactos. El modelo puede seguir agotando 12K en casos difíciles,
y se necesita una prueba real en Nobara para confirmar que la compactación
termina con `finish_reason=stop`.

## OpenCode en cualquier proyecto

`make agent PROJECT=/ruta/al/repositorio` comprueba que la API local y el
modelo configurado coinciden y abre OpenCode directamente en ese repo con
el agente **Plan**. Para editar, `make agent-build PROJECT=/ruta/al/repositorio`
exige una rama feature limpia (no `main`, `master`, `trunk` ni `production`).
Revisa los detalles en el [Quickstart](QUICKSTART.md#c-trabajar-en-un-repositorio-con-el-agente-local).

No es un sandbox; las comprobaciones ocurren antes de iniciar OpenCode y las
configuraciones locales de cada proyecto pueden alterar permisos o plugins.

## Bonsai Arena — desafío práctico aislado

`make arena` prepara un repositorio Git temporal en `/tmp/bonsai-arena-XXXXXX`
con un bug real de Python, cinco tests y `AGENTS.md`. Te indica cómo entrar
mediante `make agent-build` y puntuar la solución con
`PROJECT=/tmp/bonsai-arena-... make arena-check`. Solo aprueba si todos los
tests pasan sin modificar las pruebas ni introducir archivos inesperados.
Es una **prueba local del agente**, no una prueba CI de inferencia CUDA.

Consulta el [Quickstart](QUICKSTART.md) para los comandos completos.

## Optional systemd user service (no sudo)

To keep Bonsai running without a terminal, install a **user-scoped** unit. It
uses the same `scripts/local-ia server` launcher, so CUDA paths, model and `.env`
settings remain identical to `make server`. **Installing does not start or
activate autostart**. Starting/restarting the unit now waits until both `/health`
reports `ok` and `/v1/models` is populated, or fails with a bounded timeout:

```bash
make service-install     # install ~/.config/systemd/user/local-ia-bonsai.service
make service-start       # launch now; requires no foreground terminal
make service-status      # systemd status
make ready               # wait for /health status=ok + valid model ID
make status              # check /health and GPU process after model loads
make service-logs        # last 100 journal lines
make service-stop
```

Autostart on user login is **opt-in**. Enable it explicitly, only after the
manual start and `make smoke` work:

```bash
make service-enable      # enables on login and starts immediately
make service-disable     # disables on login and stops it
make service-uninstall   # disables, stops, removes unit and daemon-reloads
```

The generator refuses to overwrite unrelated units and never uses `sudo` or
`loginctl enable-linger`. As usual for a systemd user unit, **logging out may
stop the service** unless the host has user lingering enabled; this setup does
not change that setting. A `make service-install` after moving the checkout
regenerates its absolute path; restart the service afterward if needed.

Do not start `make server` at the same time as the service: both use the same
port. Unit logs go to the user journal; model weights, UI state, credentials,
`.env` and caches remain outside Git. Settings in `.env` are read at service
startup (not copied into the unit); restart after modifications.

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
| `BONSAI_READY_TIMEOUT` | `120` | Max seconds for `make ready` and service start/restart/enable |
| `OPENCODE_KEEP` | `2048` | Recent tokens retained in compaction |
| `OPENCODE_BUFFER` | `12288` | Token buffer; avoid V2 default 16K minimum |

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

## Repository workflow

This project is already published at [evilsysadmin/local-ia-setup](https://github.com/evilsysadmin/local-ia-setup). Use `git clone` once and `git pull --ff-only` to update. The `make publish` target is a legacy **first-time repository creation helper**, not an update command: it refuses to overwrite an existing GitHub repository. For future changes, use normal Git branches and pull requests.

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
- Structured health metrics and GPU-backed readiness verification beyond API health.

## References

- [PrismML demo and launcher](https://github.com/PrismML-Eng/Bonsai-demo)
- [OpenCode V2 custom providers](https://opencode.ai/v2/docs/providers)
- [OpenCode V2 compaction](https://opencode.ai/v2/docs/compaction)
- [OpenCode V2 policies](https://opencode.ai/v2/docs/policies)
- [OpenCode V2 permissions](https://opencode.ai/v2/docs/permissions)

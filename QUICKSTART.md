# Quickstart · local-ia-setup 🌳

Bonsai 2 27B PQ2_0 + CUDA + OpenCode V2 on **Nobara/Fedora**. Commands below run on **your own Linux machine**; this repository does **not** include model weights, credentials or conversation data.

> **Already installed Bonsai on this MSI?** Use [A](#a-bonsai-ya-instalado-docker-compose). You do **not** need to re-download ~8 GB of GGUF weights. For details and caveats, see [README](README.md).

## A. Bonsai ya instalado: Docker Compose

Necesitas Docker Engine, Docker Compose v2 y el NVIDIA Container Toolkit.
Antes del primer arranque verifica que Docker puede usar la GPU desde el checkout:

```bash
cd ~/Documents/repos/evilsysadmin/local-ia-setup
make gpu-check
```

Con eso listo, desde el checkout (y el repo ya clonado):

```bash
cd ~/Documents/repos/evilsysadmin/local-ia-setup
git pull --ff-only
make up                    # PrismML llama-server en Docker + readiness
make configure-opencode    # solo una vez, o al cambiar modelo/contexto
make agent PROJECT=~/Documents/repos/evilsysadmin/chess-studio
```

`make agent` inicia el contenedor si hace falta. Para consultar y apagar:

```bash
make browser          # abre la UI de PrismML si Bonsai está listo
make compose-ps       # también cuando todavía se esté construyendo la imagen
make compose-logs
make status
make llama-status                   # tokens, tok/s, peticiones, contexto y VRAM
make llama-status TAIL=50           # últimas 50 líneas de Docker
make llama-status TAIL=50 FOLLOW=1  # logs en tiempo real; Ctrl+C para salir
make down
```

El informe de `make llama-status` no produce una inferencia:
presenta las métricas de PrismML si `/metrics` está habilitado;
si el servidor es anterior o no las soporta, avisa sin inventar cifras.
Los contadores se reinician al arrancar de nuevo. TAIL/FOLLOW solo
leen logs de **nuestro** Compose y pueden mostrar contenido de peticiones.

Atajo para abrirlo de una sola vez: `make chat` (inicia/reutiliza el
servidor y abre tu navegador). `make browser` por sí solo no arranca
nada, comprueba el modelo y utiliza `xdg-open` o `gio open` en Nobara.

En el primer arranque, el pull/build de la imagen CUDA se muestra en
directo; `make compose-ps` da el estado del contenedor aunque no esté
corriendo. Docker Compose también admite un `BONSAI_DIR` personalizado;
sin él, su ruta predeterminada es `$HOME/Apps/Bonsai-demo`.
Ten en cuenta que los overrides de `.env` son aplicados por
`make up`, no necesariamente por una llamada manual a Docker.

El contenedor usa el GGUF, binario CUDA y scripts de
`~/Apps/Bonsai-demo` mediante **montaje de solo lectura**. La imagen
contiene CUDA, pero no copia ni vuelve a descargar el modelo. El puerto
8080 solo se publica en `127.0.0.1`. No hay autostart al iniciar sesión.

El `make gpu-check` crea un contenedor efímero, muestra GPU/VRAM y
puede descargar la imagen CUDA de prueba una sola vez. `make up`
comprueba la GPU antes de iniciar un contenedor nuevo y falla pronto
si NVIDIA Container Toolkit no funciona. CI solo prueba el código
de este check, no ejecuta la GPU real.

Si `make up` detecta un `llama-server` huérfano (como el PID 350930),
se negará a iniciar otro modelo para no consumir doble VRAM. No mata
procesos manuales: comprueba `ps -fp PID`, `ss -ltnp` y sus logs,
y detén tú el proceso antiguo si procede.

Alternativas: `make native-up`/`make native-down` usan el servicio
systemd opcional, y `make server` arranca el binario directamente en
primer plano. **No mezcles modos**.

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
make up
```

Open a **new shell** if the `opencode` command is missing after installation (or run `hash -r` to clear Bash's stale command cache). Then run `make configure-opencode` and `make agent PROJECT=...` as shown in [A](#a-bonsai-ya-instalado-docker-compose).

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

## D. Bonsai Arena: un examen práctico y reproducible 🌳

Sin tocar Chess Studio ni otros repositorios reales, crea un mini-repositorio Git
temporal con una función Python defectuosa, cinco tests y un AGENTS.md:

```bash
cd ~/Documents/repos/evilsysadmin/local-ia-setup
make arena
```

El comando imprime una ruta nueva tipo `/tmp/bonsai-arena-XXXXXX` y las
instrucciones exactas. La suite empieza fallando **deliberadamente**.
Usa la ruta realmente impresa:

```bash
PROJECT=/tmp/bonsai-arena-XXXXXX make agent-build
# En OpenCode: "Lee AGENTS.md, arregla stats.py y ejecuta los tests."
PROJECT=/tmp/bonsai-arena-XXXXXX make arena-check
```

`arena-check` solo aprueba cuando los **cinco tests** pasan, `stats.py`
ha cambiado, los tests y reglas originales siguen intactos y no aparecen
archivos adicionales. El modelo no recibe acceso automático a tus juegos,
y OpenCode sigue solicitando permisos según la configuración local. El
directorio temporal permanece para que puedas revisar el resultado.

## E. Alternative: native systemd --user (without Docker)

Instead of leaving `make server` running, after stopping it with `Ctrl+C`:

```bash
cd ~/Documents/repos/evilsysadmin/local-ia-setup
make service-install     # installs systemd --user unit; does NOT enable autostart
make service-start       # waits for model readiness; no sudo
make service-status
make smoke
```

It will **not start at login** unless you explicitly opt in with `make service-enable`. To shut down: `make service-stop`. To disable login autostart: `make service-disable`. To remove the unit: `make service-uninstall`. Logs: `make service-logs`.

Foreground, systemd and Compose all use the same port and GPU; run **only one**. The service is user-scoped; it does not enable lingering.

## Troubleshooting (the errors we actually hit)

| Symptom | What to do |
| --- | --- |
| `libcudart.so.12` or `libcublas.so.12` missing | `make install-cuda`; do not reinstall NVIDIA drivers |
| `llama-server` answers but GPU VRAM ~200 MiB | `make doctor`; check the CUDA backend plugin with `ldd`, and `nvidia-smi` |
| `No llama backend available` in Open WebUI | Read Bonsai server logs; that message may hide a CUDA/dependency problem |
| `Compaction summary reached the output token limit` | Stop resending prompts; run `make fix-compaction` to increase the small 4K buffer offline (config backup). Restart OpenCode; if the existing ~30K/32K session stays wedged, export it and continue in a new session without deleting history |
| `request (...) exceeds context` / OpenCode compaction | Make sure `BONSAI_CTX` matches the active server and re-run `make configure-opencode`; use a new OpenCode session |
| Port 8080 already bound | Reuse the running Bonsai server or stop it before switching modes |
| OpenCode V2 reported missing despite `opencode v2.x` | Update `local-ia-setup` with `git pull --ff-only`; the shared detector accepts `opencode v2.1.3`. Also try `hash -r` and inspect `type -a opencode` |

**Operational checks:**

```bash
make ready
make status
make verify              # stdlib unit tests/syntax checks; no GPU needed
nvidia-smi               # model should consume several GiB of VRAM
```

With the confirmed MSI Vector AI HX / RTX 5070 Ti Laptop setup, Bonsai generated **~45–50 tokens/s at 8K context**; your 32K context setting still needs its own performance/VRAM measurement. The `make verify` CI job does **not** prove GPU compatibility.

**Privacy:** OpenCode tools run with your user permissions, not in a sandbox. Keep the demo API and Open WebUI on loopback, and never commit `.env`, tokens, model files, or conversations.

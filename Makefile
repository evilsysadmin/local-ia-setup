.DEFAULT_GOAL := help
.PHONY: help doctor install-bonsai install-cuda install-webui install-opencode configure-opencode configure-reasoning fix-compaction server webui opencode agent agent-build agent-deep agent-build-deep arena arena-check up down browser chat gpu-check compose-logs compose-ps native-up native-down status llama-status ready smoke benchmark service-install service-start service-stop service-restart service-enable service-disable service-status service-logs service-uninstall test verify publish

help: ## Show commands
	@awk 'BEGIN {FS=":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-21s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

doctor: ## Check GPU, runtimes, dependencies, server, config
	@./scripts/local-ia doctor

install-bonsai: ## Install upstream if missing (downloads ~8 GB; existing setup preserved)
	@./scripts/local-ia install-bonsai

install-cuda: ## Install isolated CUDA 12 runtime and cuBLAS into Bonsai .venv
	@./scripts/local-ia install-cuda

install-webui: ## Install upstream-pinned Open WebUI optional extra
	@./scripts/local-ia install-webui

install-opencode: ## Install OpenCode V2 (review upstream installer beforehand)
	@./scripts/local-ia install-opencode

configure-opencode: ## Read local /v1/models and configure local-only OpenCode V2
	@./scripts/local-ia configure-opencode

configure-reasoning: ## Offline: set Bonsai medium default + selectable deep (xhigh), preserve config
	@./scripts/local-ia configure-reasoning

fix-compaction: ## Repair local OpenCode compaction buffer OFFLINE; preserve sessions and backup config
	@./scripts/local-ia fix-compaction

server: ## Start Bonsai foreground, CUDA, single slot; Ctrl+C to stop
	@./scripts/local-ia server

webui: ## Launch Open WebUI using already-running Bonsai
	@./scripts/local-ia webui

opencode: ## Start OpenCode from this checkout (legacy low-level command)
	@./scripts/local-ia opencode

agent: ## Open Bonsai Plan in a project: make agent PROJECT=/path/to/repo
	@./scripts/local-ia agent

agent-build: ## Open Bonsai Build (requires clean feature branch)
	@./scripts/local-ia agent-build

agent-deep: ## Open Bonsai Plan with deep (xhigh) effort in target Git repo
	@./scripts/local-ia agent-deep

agent-build-deep: ## Open Bonsai Build (xhigh, requires clean feature branch)
	@./scripts/local-ia agent-build-deep

arena: ## Generate an isolated coding challenge and instructions
	@./scripts/local-ia arena

arena-check: ## Score arena: PROJECT=/tmp/bonsai-arena-... make arena-check
	@./scripts/local-ia arena-check

up: ## Start PrismML CUDA in Docker Compose (or reuse an existing local Bonsai)
	@./scripts/local-ia up

browser: ## Open ready PrismML UI in your desktop browser (no implicit startup)
	@./scripts/local-ia browser

chat: ## Start/reuse Bonsai and open its local browser chat
	@./scripts/local-ia up
	@./scripts/local-ia browser

down: ## Stop only our Docker Compose stack (never kill a manual server)
	@./scripts/local-ia down

gpu-check: ## Check NVIDIA GPU access INSIDE Docker (downloads CUDA probe image if needed)
	@./scripts/local-ia gpu-check

compose-ps: ## Show status of Bonsai's Compose container (no env exports needed)
	@./scripts/local-ia compose-ps

compose-logs: ## Last 100 log lines from our Bonsai Compose container
	@./scripts/local-ia compose-logs

native-up: ## Optional fallback: start Bonsai via systemd --user
	@./scripts/local-ia native-up

native-down: ## Optional fallback: stop only the managed systemd --user unit
	@./scripts/local-ia native-down

status: ## Quick API and GPU status
	@./scripts/local-ia status

llama-status: ## Llama metrics + optional logs: TAIL=50 FOLLOW=1
	@./scripts/local-ia llama-status

ready: ## Wait up to BONSAI_READY_TIMEOUT for model readiness (not just process startup)
	@./scripts/local-ia ready

smoke: ## Check API and run a short completion (requires running server)
	@./scripts/local-ia smoke

benchmark: ## Run one repeatable timed completion; no claims about GPU rate
	@./scripts/local-ia benchmark


service-install: ## Install optional systemd --user Bonsai unit (does not start/enable)
	@./scripts/local-ia service-install

service-start: ## Start user service (manual, no login autostart)
	@./scripts/local-ia service-start

service-stop: ## Stop user service
	@./scripts/local-ia service-stop

service-restart: ## Restart user service after changing .env or code
	@./scripts/local-ia service-restart

service-enable: ## Enable service at login AND start now (explicit opt-in)
	@./scripts/local-ia service-enable

service-disable: ## Disable login autostart and stop service
	@./scripts/local-ia service-disable

service-status: ## Inspect systemd --user service state
	@./scripts/local-ia service-status

service-logs: ## Last 100 Bonsai service journal lines
	@./scripts/local-ia service-logs

service-uninstall: ## Disable, stop and remove only our generated service
	@./scripts/local-ia service-uninstall

test: ## Pure standard-library unit tests
	@python3 -m unittest discover -s tests -v

publish: verify ## Create evilsysadmin/local-ia-setup on GitHub (private by default; requires gh)
	@./scripts/publish.sh

verify: test ## Local static validation
	@bash -n scripts/local-ia scripts/publish.sh
	@python3 -m py_compile scripts/local_setup.py scripts/user_service.py scripts/agent_launcher.py scripts/arena.py scripts/lifecycle.py scripts/compose_lifecycle.py scripts/browser.py scripts/llama_status.py
	@echo 'Static checks: OK'

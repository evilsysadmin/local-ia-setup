.DEFAULT_GOAL := help
.PHONY: help doctor install-bonsai install-cuda install-webui install-opencode configure-opencode server webui opencode status ready smoke benchmark service-install service-start service-stop service-restart service-enable service-disable service-status service-logs service-uninstall test verify publish

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

server: ## Start Bonsai foreground, CUDA, single slot; Ctrl+C to stop
	@./scripts/local-ia server

webui: ## Launch Open WebUI using already-running Bonsai
	@./scripts/local-ia webui

opencode: ## Start OpenCode with configured local provider
	@./scripts/local-ia opencode

status: ## Quick API and GPU status
	@./scripts/local-ia status

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
	@python3 -m py_compile scripts/local_setup.py scripts/user_service.py
	@echo 'Static checks: OK'

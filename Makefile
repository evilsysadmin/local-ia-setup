.DEFAULT_GOAL := help
.PHONY: help doctor install-bonsai install-cuda install-webui install-opencode configure-opencode server webui opencode status smoke benchmark test verify publish

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

smoke: ## Check API and run a short completion (requires running server)
	@./scripts/local-ia smoke

benchmark: ## Run one repeatable timed completion; no claims about GPU rate
	@./scripts/local-ia benchmark

test: ## Pure standard-library unit tests
	@python3 -m unittest discover -s tests -v

publish: verify ## Create evilsysadmin/local-ia-setup on GitHub (private by default; requires gh)
	@./scripts/publish.sh

verify: test ## Local static validation
	@bash -n scripts/local-ia scripts/publish.sh
	@python3 -m py_compile scripts/local_setup.py
	@echo 'Static checks: OK'

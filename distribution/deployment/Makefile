# Standalone container operations; no harness or host Python required.
#
# `make` and `make help` are read-only: they list the available commands and
# need neither Docker, Python nor deployment.env. Startup is always explicit.
.DEFAULT_GOAL := help
ifeq ($(OS),Windows_NT)
# Use PowerShell 7 when installed, independent of the shell that invoked Make.
WINDOWS_PS := $(if $(filter %pwsh.exe,$(shell where.exe pwsh.exe 2>&1)),pwsh.exe,powershell.exe)
PS_SCRIPT = $(WINDOWS_PS) -NoProfile -File
COMPOSE = $(PS_SCRIPT) ./compose.ps1
URL = $(PS_SCRIPT) ./url.ps1
else
COMPOSE = bash ./compose.sh
URL = bash ./url.sh
endif
CLI = $(COMPOSE) exec -T production python -m pi_platform.cli
WAIT_TIMEOUT ?= 1800
# An explicitly empty value leaves the policy to deployment.env.
ALLOW_SKIPPED_SOURCES ?= 1
ifneq ($(strip $(ALLOW_SKIPPED_SOURCES)),)
ifeq ($(ALLOW_SKIPPED_SOURCES),1)
export PI_INDEX_REQUIRE_COMPLETE := 0
else ifeq ($(ALLOW_SKIPPED_SOURCES),0)
export PI_INDEX_REQUIRE_COMPLETE := 1
else
$(error ALLOW_SKIPPED_SOURCES must be 1 or 0)
endif
endif
MODEL ?= gemma
LLAMA_PORT ?= 8769
LLAMA_AUTH ?= managed-token
GPU ?= vulkan
# LLM is deliberately unset: normal startup preserves existing UI configuration.
# Values are exported by NAME, never interpolated into shell command text.
LLM ?=
LLM_ENABLED ?= 1
export LLM_PROVIDER LLM_URL LLM_MODEL LLM_API_KEY LLM_SHARE_CONTEXT LLM_ENABLED
CHAT_RUN = $(COMPOSE) run --rm --no-deps -T -e LLM_PROVIDER -e LLM_URL -e LLM_MODEL -e LLM_API_KEY -e LLM_SHARE_CONTEXT -e LLM_ENABLED production chat

ifeq ($(LLM),1)
platform-start: platform-llm-configure
else ifeq ($(LLM),0)
platform-start: platform-llm-disable
else ifneq ($(strip $(LLM)),)
$(error LLM must be 1 to configure/enable, 0 to disable, or omitted to preserve settings)
endif

.PHONY: help platform-start platform-stop platform-status platform-logs platform-pull platform-restart platform-init platform-hydrate platform-materialise platform-models platform-assets platform-model-pull platform-reindex platform-doctor platform-llm-configure platform-llm-status platform-llm-test platform-llm-disable platform-llama-start platform-llama-connect platform-trust-setup platform-gpu-install platform-index-failures eval eval-retrieval eval-chunk-size-sweep invariants metrics-gate

help: ## List every command with a one-line description (default; changes nothing)
ifeq ($(OS),Windows_NT)
	@$(PS_SCRIPT) ./help.ps1
else
	@printf '%s\n' "Project Intelligence deployment kit -- available commands"
	@printf '%s\n' ""
	@awk '{ line = $$0; colon = index(line, ":"); if (colon == 0) next; name = substr(line, 1, colon - 1); if (name !~ /^[A-Za-z0-9][A-Za-z0-9_.-]*$$/) next; rest = substr(line, colon + 1); mark = index(rest, "##"); if (mark == 0) next; desc = substr(rest, mark + 2); gsub(/^[[:space:]]+/, "", desc); gsub(/[[:space:]]+$$/, "", desc); printf "  make %-22s %s\n", name, desc; }' $(MAKEFILE_LIST)
	@printf '%s\n' ""
	@printf '%s\n' "Startup is explicit: run 'make platform-start'. Optional: LLM=1 (configure), LLM=0 (disable), ALLOW_SKIPPED_SOURCES=0 (require complete indexing)."
endif

platform-start: ## Start the services and print the browser URL
	$(COMPOSE) up -d --wait --wait-timeout $(WAIT_TIMEOUT)
	@$(URL)

platform-llama-start: export PI_LLAMA_PORT = $(LLAMA_PORT)
platform-llama-start: export PI_SIDECAR_LLAMA_AUTH = $(LLAMA_AUTH)
platform-llama-start: ## Start ProjectExpert with its pinned embedding server (LLAMA_PORT, LLAMA_AUTH)
	$(COMPOSE) up -d --wait --wait-timeout $(WAIT_TIMEOUT)
	@$(URL)

platform-llama-connect: ## Connect a running native Windows llama-server (LLAMA_PORT, LLAMA_AUTH, LLAMA_TOKEN_FILE)
platform-trust-setup: ## Refresh public host CA roots for container HTTPS
platform-gpu-install: ## Prepare the pinned GPU runtime (GPU=cuda or GPU=vulkan)

ifeq ($(OS),Windows_NT)
platform-llama-connect: export PI_LLAMA_PORT = $(LLAMA_PORT)
platform-llama-connect: export PI_NATIVE_LLAMA_AUTH = $(LLAMA_AUTH)
platform-llama-connect: export PI_NATIVE_LLAMA_TOKEN_FILE = $(LLAMA_TOKEN_FILE)
platform-llama-connect:
	$(PS_SCRIPT) ./llama-connect.ps1
platform-trust-setup:
	$(PS_SCRIPT) ./host-trust.ps1
ifeq ($(GPU),cuda)
platform-gpu-install: export PI_GPU_PACK_ROOT = $(GPU_PACK)
platform-gpu-install: export PI_GPU_PACK_SHA256 = $(GPU_PACK_SHA256)
platform-gpu-install:
	$(PS_SCRIPT) ./native-cuda.ps1 -Action install
else ifeq ($(GPU),vulkan)
platform-gpu-install:
	$(PS_SCRIPT) ./setup-windows-accelerator.ps1 -Backend vulkan -AssetsOnly
else
platform-gpu-install:
	@echo GPU must be cuda or vulkan
	@exit 2
endif
else
platform-llama-connect:
	@printf '%s\n' 'Native Windows connection is only available on Windows. Use platform-llama-start for the Linux sidecar.' >&2
	@exit 2
platform-trust-setup:
	bash ./host-trust.sh
platform-gpu-install: export PI_GPU_INSTALL_BACKEND = $(GPU)
platform-gpu-install:
	bash ./compose.sh gpu-install
endif
platform-llm-configure: ## Save optional chat settings before startup (LLM_URL, LLM_MODEL, LLM_SHARE_CONTEXT=1)
	$(CHAT_RUN) configure --from-env --enable --target /repo
platform-llm-status: ## Show the same saved chat configuration as the UI (provider key hidden)
	$(COMPOSE) run --rm --no-deps -T production chat status --target /repo
platform-llm-test: ## Test the saved chat connection before startup (no project context sent)
	$(COMPOSE) run --rm --no-deps -T production chat test --target /repo
platform-llm-disable: ## Disable generated answers while preserving saved endpoint and provider key
	$(COMPOSE) run --rm --no-deps -T production chat disable --target /repo
platform-stop: ## Stop the deployment containers and keep the model cache
	$(COMPOSE) down
platform-status: ## Show the running containers and the retrieval readiness
	$(COMPOSE) ps
	$(CLI) health --ready --target /repo
platform-logs: ## Follow the container logs
	$(COMPOSE) logs --tail 100 -f
platform-pull: ## Pull the pinned application and runtime images
	$(COMPOSE) pull
platform-restart: ## Restart the deployment containers without changing the configuration
	$(COMPOSE) restart
	$(COMPOSE) up -d --wait --wait-timeout $(WAIT_TIMEOUT)
platform-init: ## Create the project structure in the target repository
	$(COMPOSE) run --rm --no-deps production init-project --target /repo
platform-hydrate: ## Re-index the target repository with the current configuration
	$(CLI) hydrate --target /repo
platform-materialise: ## Write the reviewed materialisation into the target repository
	$(CLI) materialise --target /repo --approval-token "$(APPROVAL_TOKEN)"
platform-models: ## Show the embedding model status of the deployment
	$(CLI) models status --target /repo
platform-model-pull: ## Explicit developer model pull (disabled for production offline deployments)
	$(CLI) models pull "$(MODEL)" --target /repo
platform-reindex: ## Rebuild the retrieval index for the target repository
	$(CLI) reindex --target /repo
platform-index-failures: ## Show the private source-stage report (includes repository file paths)
	$(COMPOSE) run --rm --no-deps -T production source-failures --target /repo
platform-doctor: ## Diagnose the deployment runtime and the retrieval configuration
	$(CLI) doctor --target /repo
eval: ## Run the retrieval evaluation against the bundled fixture benchmark
	$(CLI) eval
eval-retrieval: ## Run the retrieval evaluation without the stored baseline
	$(CLI) eval-retrieval --no-baseline
eval-chunk-size-sweep: ## Measure the retrieval quality across chunk sizes
	$(CLI) eval-chunk-size-sweep
invariants: ## Check the repository invariants of the target project
	$(CLI) invariants
metrics-gate: ## Evaluate the retrieval metrics against the configured gate
	$(CLI) metrics-gate

platform-assets: ## Show running image IDs and verify the active offline asset manifest
	$(COMPOSE) images
	$(COMPOSE) exec -T production python -m pi_platform.deployment.offline_assets

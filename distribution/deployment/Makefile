# Standalone container operations; no harness or host Python required.
#
# `make` and `make help` are read-only: they list the available commands and
# need neither Docker, Python nor deployment.env. Startup is always explicit.
.DEFAULT_GOAL := help
ifeq ($(OS),Windows_NT)
COMPOSE = powershell -NoProfile -File ./compose.ps1
URL = powershell -NoProfile -File ./url.ps1
else
COMPOSE = bash ./compose.sh
URL = bash ./url.sh
endif
CLI = $(COMPOSE) exec -T production python -m pi_platform.cli
WAIT_TIMEOUT ?= 1800
MODEL ?= gemma
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

.PHONY: help platform-start platform-stop platform-status platform-logs platform-pull platform-restart platform-init platform-hydrate platform-materialise platform-models platform-model-pull platform-reindex platform-doctor platform-llm-configure platform-llm-status platform-llm-test platform-llm-disable eval eval-retrieval eval-chunk-size-sweep invariants metrics-gate

help: ## List every command with a one-line description (default; changes nothing)
	@printf '%s\n' "Project Intelligence deployment kit -- available commands"
	@printf '%s\n' ""
	@awk '{ line = $$0; colon = index(line, ":"); if (colon == 0) next; name = substr(line, 1, colon - 1); if (name !~ /^[A-Za-z0-9][A-Za-z0-9_.-]*$$/) next; rest = substr(line, colon + 1); mark = index(rest, "##"); if (mark == 0) next; desc = substr(rest, mark + 2); gsub(/^[[:space:]]+/, "", desc); gsub(/[[:space:]]+$$/, "", desc); printf "  make %-22s %s\n", name, desc; }' $(MAKEFILE_LIST)
	@printf '%s\n' ""
	@printf '%s\n' "Startup is explicit: run 'make platform-start'. Optional: LLM=1 (configure), LLM=0 (disable)."

platform-start: ## Start the deployment and wait until the service reports readiness
	$(COMPOSE) up -d --wait --wait-timeout $(WAIT_TIMEOUT)
	@$(URL)
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
platform-model-pull: ## Download the selected embedding model into the model cache
	$(CLI) models pull "$(MODEL)" --target /repo
platform-reindex: ## Rebuild the retrieval index for the target repository
	$(CLI) reindex --target /repo
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

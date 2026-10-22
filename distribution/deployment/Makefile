# Standalone container operations; no harness or host Python required.
.DEFAULT_GOAL := platform-start
ifeq ($(OS),Windows_NT)
COMPOSE = powershell -NoProfile -File ./compose.ps1
else
COMPOSE = bash ./compose.sh
endif
CLI = $(COMPOSE) exec -T production python -m pi_platform.cli
WAIT_TIMEOUT ?= 1800
MODEL ?= qwen

.PHONY: platform-start platform-stop platform-status platform-logs platform-pull platform-restart platform-init platform-hydrate platform-materialise platform-models platform-model-pull platform-reindex platform-doctor eval eval-retrieval eval-chunk-size-sweep invariants metrics-gate
platform-start:
	$(COMPOSE) up -d --wait --wait-timeout $(WAIT_TIMEOUT)
	@echo "Ready. Open http://localhost:$${PI_CONTROL_PORT:-8765} (or the port in deployment.env)."
platform-stop:
	$(COMPOSE) down
platform-status:
	$(COMPOSE) ps
	$(CLI) health --ready --target /repo
platform-logs:
	$(COMPOSE) logs --tail 100 -f
platform-pull:
	$(COMPOSE) pull
platform-restart:
	$(COMPOSE) restart
	$(COMPOSE) up -d --wait --wait-timeout $(WAIT_TIMEOUT)
platform-init:
	$(COMPOSE) run --rm --no-deps production init-project --target /repo
platform-hydrate:
	$(CLI) hydrate --target /repo
platform-materialise:
	$(CLI) materialise --target /repo --approval-token "$(APPROVAL_TOKEN)"
platform-models:
	$(CLI) models status --target /repo
platform-model-pull:
	$(CLI) models pull "$(MODEL)" --target /repo
platform-reindex:
	$(CLI) reindex --target /repo
platform-doctor:
	$(CLI) doctor --target /repo
eval:
	$(CLI) eval
eval-retrieval:
	$(CLI) eval-retrieval --no-baseline
eval-chunk-size-sweep:
	$(CLI) eval-chunk-size-sweep
invariants:
	$(CLI) invariants
metrics-gate:
	$(CLI) metrics-gate

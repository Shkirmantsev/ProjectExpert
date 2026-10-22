.DEFAULT_GOAL := help
ifeq ($(OS),Windows_NT)
PYTHON ?= python
else
PYTHON ?= python3
endif
STACK := $(PYTHON) scripts/stack.py

.PHONY: help init init-mcp env-sync runtime check wiki-index wiki-validate openspec-check mcp-install \
        config plan pull build up start stop restart down status ps logs client-config \
        skills-sync-local skills-sync-remote skills-check manifest-generate manifest-check hermes-host-setup hermes-host-revoke \
        hermes-sidecar-copy hermes-remote-instructions hermes-patch hermes-check hermes-import verify verify-models test clean \
        platform-init platform-hydrate platform-materialise license gate license-gate okf-validate \
        version-identity wal-recover platform-test eval eval-baseline eval-retrieval eval-chunk-size-sweep invariants metrics-gate phase-10-test

help: ## Show all harness commands without a POSIX shell dependency.
	@$(PYTHON) harness.py help

init: ## Portable core init; also disables telemetry when OpenSpec is installed.
	@$(PYTHON) harness.py init

init-mcp: ## Init core (including OpenSpec opt-out) and install project-context MCP.
	@$(PYTHON) harness.py init --install-mcp

env-sync: ## Add new .env.example variables without overwriting existing values.
	@$(PYTHON) scripts/bootstrap_env.py

runtime: ## Refresh auto identities and generated client files.
	@$(PYTHON) scripts/bootstrap_env.py
	@$(PYTHON) harness.py client-config

check: ## Validate config, Wiki, OpenSpec structure, and run core tests.
	@$(PYTHON) harness.py check

wiki-index: ## Rebuild disposable SQLite FTS index from canonical Markdown Wiki.
	@$(PYTHON) harness.py index

wiki-validate: ## Validate Wiki stable IDs and links.
	@$(PYTHON) harness.py wiki-validate

openspec-check: ## Validate production-sdd structure; invoke OpenSpec CLI when installed.
	@$(PYTHON) harness.py openspec-check

manifest-generate: ## Regenerate the deterministic source artifact manifest.
	@$(PYTHON) harness.py manifest-generate

manifest-check: ## Verify the deterministic source artifact manifest.
	@$(PYTHON) harness.py manifest-check

mcp-install: ## Install project-context MCP into tmp/local/project-context/venv.
	@$(PYTHON) harness.py mcp-install

client-config: ## Generate Claude/OpenCode/Codex configs; OpenCode V1 stable is default, V2 beta is opt-in.
	@$(PYTHON) harness.py client-config

config: ## Render Docker Compose configuration for enabled optional LOCAL features.
	@$(STACK) config

plan: ## Show enabled optional local services and remote Hermes status.
	@$(STACK) plan

pull: ## Pull images for enabled optional local features.
	@$(STACK) pull

build: ## Build local harness images for enabled optional local features.
	@$(STACK) build

up: check client-config ## Reconcile and start enabled optional LOCAL features.
	@$(STACK) up

start: ## Start already-created optional containers.
	@$(STACK) start

stop: ## Stop ALL harness containers, including old profiles.
	@$(STACK) stop

restart: ## Reconcile and restart enabled optional local stack.
	@$(MAKE) --no-print-directory down
	@$(MAKE) --no-print-directory up

down: ## Stop/remove ALL harness containers/network.
	@$(STACK) down

status: ## Show ALL harness containers.
	@$(STACK) status

ps: status ## Alias for status.

logs: ## Show recent logs for ALL harness containers; ARGS='-f' follows.
	@$(STACK) logs $(ARGS)

skills-sync-local: ## Sync Claude/OpenCode core skills and validate all canonical Codex skills.
	@$(PYTHON) scripts/sync_skills.py local

skills-sync-remote: ## Rsync routed core skills to optional remote Hermes profile.
	@$(PYTHON) scripts/sync_skills.py remote

skills-check: ## Verify client mirrors and all canonical Codex skill availability.
	@$(PYTHON) scripts/sync_skills.py check

hermes-host-setup: ## Optional: configure unprivileged main-PC Hermes access.
	@$(PYTHON) scripts/hermes_host_setup.py $(if $(filter 1 true yes,$(ENABLE_TAILSCALE_SSH)),--yes-enable-tailscale-ssh,)

hermes-host-revoke: ## Optional: remove this project's ACL from dedicated Hermes user.
	@$(PYTHON) scripts/hermes_host_setup.py --revoke

hermes-sidecar-copy: ## Optional: copy Claude-specific Hermes MCP sidecar source to remote host.
	@$(PYTHON) scripts/copy_remote_sidecar.py

hermes-remote-instructions: ## Optional: generate remote Hermes setup instructions.
	@$(PYTHON) scripts/render_hermes_remote_setup.py

hermes-patch: ## Optional: re-apply the harness resolver patch on the remote Hermes source.
	@$(PYTHON) scripts/hermes_patch.py

hermes-check: ## Optional: verify remote Hermes control paths without paid inference.
	@$(PYTHON) scripts/verify.py --only-hermes

hermes-import: ## Optional: stage external file into PROJECT_ROOT/.harness/inbox. FILE=/path/file
	@$(PYTHON) scripts/hermes_import.py $(if $(FILE),"$(FILE)",)

verify: ## Verify enabled optional services; remote inference is NOT RUN by default.
	@$(PYTHON) scripts/verify.py

verify-models: ## Verify configured optional local/LiteLLM model aliases.
	@$(PYTHON) scripts/verify_models.py

test: ## Run core tests without requiring Docker/Tailscale.
	@$(PYTHON) harness.py test

# ---------------------------------------------------------------------------
# Phase 1 v0.8 Project Intelligence Platform targets.
# ---------------------------------------------------------------------------

platform-init: ## Initialise a target project with the Phase 1 foundation.
	@$(PYTHON) -m pi_platform.cli init-project --target ${TARGET:-.}

platform-hydrate: ## Restore the runtime cache from the canonical tree.
	@$(PYTHON) -m pi_platform.cli hydrate --target ${TARGET:-.}

platform-materialise: ## Write durable changes back to the canonical tree (approval-gated).
	@$(PYTHON) -m pi_platform.cli materialise --target ${TARGET:-.} --approval-token ${APPROVAL_TOKEN:-manual}

license-gate: ## Run the CI license gate against the dependency inventory.
	@$(PYTHON) -m pi_platform.cli license-gate --target ${TARGET:-.}

okf-validate: ## Validate a Wiki bundle against the OKF v0.2 profile.
	@$(PYTHON) -m pi_platform.cli okf-validate --wiki-root ${WIKI_ROOT:-project-knowledge/wiki}

version-identity: ## Compute the runtime project version identity.
	@$(PYTHON) -m pi_platform.cli version-identity --target ${TARGET:-.}

wal-recover: ## Recover a crashed materialise from the write-ahead log.
	@$(PYTHON) -m pi_platform.cli wal-recover --cache-root ${CACHE_ROOT:-.project-intelligence-cache}

platform-test: ## Run the Phase 1 platform regression suite.
	@$(PYTHON) -m unittest discover -s tests -p "test_platform_*.py" -v

# ---------------------------------------------------------------------------
# Phase 10 §49 + §120 quality-gates targets
# ---------------------------------------------------------------------------

eval: ## Run the §49 integration-quality-gates suites.
	@$(PYTHON) -m pi_platform.cli eval

eval-baseline: ## Print the recorded Tier-1 pre-change evaluation baseline.
	@$(PYTHON) scripts/eval_baseline.py show

eval-retrieval: ## Run the v0.8 Tier-3 retrieval evaluation against the golden query set.
	@$(PYTHON) -m pi_platform.cli eval-retrieval

eval-chunk-size-sweep: ## Sweep the v0.8 Tier-3 chunk-size budgets and pick the default.
	@$(PYTHON) -m pi_platform.cli eval-chunk-size-sweep

invariants: ## Run the §120 52-invariant §68 acceptance suite.
	@$(PYTHON) -m pi_platform.cli invariants

metrics-gate: ## Verify the last eval/last.json metrics are within the documented thresholds.
	@$(PYTHON) -m pi_platform.cli metrics-gate

phase-10-test: ## Run the four Phase 10 test modules + adversarial probe coverage in one shot.
	@$(PYTHON) -m unittest tests.test_phase_10_a2a tests.test_phase_10_quality_gates tests.test_phase_10_invariants tests.test_phase_10_schema_migration tests.test_phase_10_adversarial -v

clean: ## Remove generated clients/index/runtime state; preserve .env and source.
	@$(PYTHON) harness.py clean


# Portable manual MCP lifecycle; configured stdio clients still own their processes.
run-mcp: ## Start connectable background MCP on Windows, Linux or macOS.
	@$(PYTHON) harness.py run-mcp

mcp-run: run-mcp ## Alias of run-mcp.

stop-mcp: ## Stop the background MCP started by run-mcp.
	@$(PYTHON) harness.py stop-mcp

mcp-stop: stop-mcp ## Alias of stop-mcp.

mcp-status: ## Show whether background project-context MCP is ready.
	@$(PYTHON) harness.py mcp-status

mcp-logs: ## Show the recent project-context MCP log.
	@$(PYTHON) harness.py mcp-logs

mcp-clean: ## Remove stopped background MCP state and log files.
	@$(PYTHON) harness.py mcp-clean

mcp-stdio: ## Run foreground MCP stdio for a client.
	@$(PYTHON) harness.py mcp-stdio

wiki-init: ## Validate existing Wiki and initialize its local index.
	@$(PYTHON) harness.py wiki-init

init-wiki: wiki-init ## Alias of wiki-init.

check-delegated: ## Run secret-free CI verification.
	@$(PYTHON) harness.py check-delegated

# Donor-compatible harness names for embedding beside product Make targets.

harness-init: init ## Alias of init.

harness-init-mcp: init-mcp ## Alias of init-mcp.

harness-mcp-install: mcp-install ## Alias of mcp-install.

harness-client-config: client-config ## Alias of client-config.

harness-check: check ## Alias of check.

harness-check-delegated: check-delegated ## Alias of check-delegated.

harness-test: test ## Alias of test.

harness-wiki-index: wiki-index ## Alias of wiki-index.

harness-wiki-validate: wiki-validate ## Alias of wiki-validate.

harness-openspec-check: openspec-check ## Alias of openspec-check.

harness-manifest-generate: manifest-generate ## Alias of manifest-generate.

harness-manifest-check: manifest-check ## Alias of manifest-check.

harness-clean: clean ## Alias of clean.

.PHONY: run-mcp mcp-run stop-mcp mcp-stop mcp-status mcp-logs mcp-clean mcp-stdio wiki-init init-wiki check-delegated harness-init harness-init-mcp harness-mcp-install harness-client-config harness-check harness-check-delegated harness-test harness-wiki-index harness-wiki-validate harness-openspec-check harness-manifest-generate harness-manifest-check harness-clean \
        pi-help pi-up pi-model pi-status pi-reindex pi-doctor pi-down

# ---------------------------------------------------------------------------
# One-command Production UX product targets (PR 11, plan §15–§18, §55–§60).
# ---------------------------------------------------------------------------

PI_TARGET ?= $(or $(TARGET),.)
PI_MODEL ?= $(or $(MODEL),gemma)
PI_DEVICE ?= $(or $(DEVICE),auto)
PI_HOST ?= $(or $(HOST),127.0.0.1)
PI_PORT ?= $(or $(PORT),8765)

pi-help: ## Show the user-facing Project Intelligence product commands.
	@echo "Project Intelligence — One-Command Product Surface:"
	@echo "  make pi-up [TARGET=/path/to/repo] [MODEL=gemma|qwen] [DEVICE=auto|cpu|cuda] [SERVE=1]"
	@echo "      Initialise, hydrate, discover sources, build semantic index, and start platform."
	@echo "  make pi-model MODEL=gemma|qwen [TARGET=/path/to/repo]"
	@echo "      Switch active embedding model and atomically activate its vector namespace."
	@echo "  make pi-status [TARGET=/path/to/repo]"
	@echo "      Show active embedding model, profile identity, dense index generation, and readiness."
	@echo "  make pi-reindex [TARGET=/path/to/repo]"
	@echo "      Run incremental source discovery, reconciliation, and index refresh."
	@echo "  make pi-doctor [TARGET=/path/to/repo]"
	@echo "      Run production capability gate and target repository health diagnostics."
	@echo "  make pi-down"
	@echo "      Stop running Project Intelligence product containers."

pi-up: ## Start Project Intelligence against TARGET with MODEL (gemma|qwen) and DEVICE (auto|cpu|cuda).
	@if [ "$(DOCKER)" = "1" ]; then \
		PI_TARGET_REPO="$(PI_TARGET)" PI_EMBEDDING_MODEL="$(PI_MODEL)" PI_EMBEDDING_DEVICE="$(PI_DEVICE)" \
		docker compose --profile production up -d --build; \
	else \
		$(PYTHON) -m pi_platform.cli start --target "$(PI_TARGET)" --model "$(PI_MODEL)" --device "$(PI_DEVICE)" --host "$(PI_HOST)" --port "$(PI_PORT)" $(if $(filter 1 true yes,$(SERVE)),--serve,); \
	fi

pi-model: ## Switch MODEL in the active host or Docker deployment without changing canonical knowledge.
	@if [ "$(DOCKER)" = "1" ]; then \
		PI_TARGET_REPO="$(PI_TARGET)" PI_EMBEDDING_MODEL="$(PI_MODEL)" PI_EMBEDDING_DEVICE="$(PI_DEVICE)" \
		docker compose --profile production up -d --force-recreate production; \
	else \
		$(PYTHON) -m pi_platform.cli models use "$(PI_MODEL)" --target "$(PI_TARGET)" && \
		$(PYTHON) -m pi_platform.cli reindex --target "$(PI_TARGET)"; \
	fi

pi-status: ## Show model profile and retrieval index status in the active host or Docker deployment.
	@if [ "$(DOCKER)" = "1" ]; then \
		PI_TARGET_REPO="$(PI_TARGET)" docker compose --profile production exec -T production python -m pi_platform.cli models status --target /repo && \
		PI_TARGET_REPO="$(PI_TARGET)" docker compose --profile production exec -T production python -m pi_platform.cli retrieval-status --target /repo; \
	else \
		$(PYTHON) -m pi_platform.cli models status --target "$(PI_TARGET)" && \
		$(PYTHON) -m pi_platform.cli retrieval-status --target "$(PI_TARGET)"; \
	fi

pi-reindex: ## Refresh indexes in the active host or Docker deployment.
	@if [ "$(DOCKER)" = "1" ]; then \
		PI_TARGET_REPO="$(PI_TARGET)" docker compose --profile production exec -T production python -m pi_platform.cli reindex --target /repo; \
	else \
		$(PYTHON) -m pi_platform.cli reindex --target "$(PI_TARGET)"; \
	fi

pi-doctor: ## Check production readiness in the active host or Docker deployment.
	@if [ "$(DOCKER)" = "1" ]; then \
		PI_TARGET_REPO="$(PI_TARGET)" docker compose --profile production exec -T production python -m pi_platform.cli doctor --target /repo; \
	else \
		$(PYTHON) -m pi_platform.cli doctor --target "$(PI_TARGET)"; \
	fi

pi-down: ## Stop Project Intelligence production containers.
	@docker compose --profile production down 2>/dev/null || true

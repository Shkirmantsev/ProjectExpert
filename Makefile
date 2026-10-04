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
        hermes-sidecar-copy hermes-remote-instructions hermes-check hermes-import verify verify-models test clean \
        platform-init platform-hydrate platform-materialise license gate license-gate okf-validate \
        version-identity wal-recover platform-test

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

skills-sync-local: ## Sync directly discoverable routed core skills into Claude and OpenCode project directories.
	@$(PYTHON) scripts/sync_skills.py local

skills-sync-remote: ## Rsync routed core skills to optional remote Hermes profile.
	@$(PYTHON) scripts/sync_skills.py remote

skills-check: ## Verify Claude/OpenCode skill exposure and catalog isolation.
	@$(PYTHON) scripts/sync_skills.py check

hermes-host-setup: ## Optional: configure unprivileged main-PC Hermes access.
	@$(PYTHON) scripts/hermes_host_setup.py $(if $(filter 1 true yes,$(ENABLE_TAILSCALE_SSH)),--yes-enable-tailscale-ssh,)

hermes-host-revoke: ## Optional: remove this project's ACL from dedicated Hermes user.
	@$(PYTHON) scripts/hermes_host_setup.py --revoke

hermes-sidecar-copy: ## Optional: copy Claude-specific Hermes MCP sidecar source to remote host.
	@$(PYTHON) scripts/copy_remote_sidecar.py

hermes-remote-instructions: ## Optional: generate remote Hermes setup instructions.
	@$(PYTHON) scripts/render_hermes_remote_setup.py

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

.PHONY: run-mcp mcp-run stop-mcp mcp-stop mcp-status mcp-logs mcp-clean mcp-stdio wiki-init init-wiki check-delegated harness-init harness-init-mcp harness-mcp-install harness-client-config harness-check harness-check-delegated harness-test harness-wiki-index harness-wiki-validate harness-openspec-check harness-manifest-generate harness-manifest-check harness-clean

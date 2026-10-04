SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help
.PHONY: help init check venv import-api-key install up start stop restart status logs verify test clean

help: ## Show sidecar management commands.
	@printf "\nHermes Native Claude MCP Sidecar\n\n"
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_.-]+:.*## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

init: ## Create .env and generate the sidecar bearer token.
	@python3 scripts/bootstrap_env.py

check: ## Validate sidecar configuration without starting services.
	@python3 scripts/check_config.py

venv: ## Create/update the isolated Python venv and install this sidecar.
	@python3 -m venv .venv
	@.venv/bin/pip install --upgrade pip
	@.venv/bin/pip install -e .

import-api-key: ## Securely copy the existing worker profile API_SERVER_KEY into sidecar .env.
	@python3 scripts/import_api_key.py

install: venv ## Install/enable the user systemd unit (does not rotate Hermes credentials).
	@python3 scripts/install_service.py
	@systemctl --user daemon-reload
	@systemctl --user enable hermes-worker-mcp.service

up: check ## Start the sidecar service.
	@systemctl --user start hermes-worker-mcp.service

start: up ## Alias for up.

stop: ## Stop the sidecar service.
	@systemctl --user stop hermes-worker-mcp.service

restart: check ## Restart sidecar after configuration changes.
	@systemctl --user restart hermes-worker-mcp.service

status: ## Show sidecar status.
	@systemctl --user status --no-pager hermes-worker-mcp.service

logs: ## Follow sidecar logs.
	@journalctl --user -u hermes-worker-mcp.service -f

verify: ## Verify native Hermes API + protected sidecar health.
	@python3 scripts/verify.py

test: ## Run package tests that do not need network/systemd.
	@PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v

clean: ## Remove only local venv/cache; preserve .env and systemd service.
	@rm -rf .venv __pycache__ src/*.egg-info src/hermes_native_claude_mcp.egg-info
	@find . -type d -name __pycache__ -prune -exec rm -rf {} +

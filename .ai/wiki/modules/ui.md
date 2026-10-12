---
id: modules.ui
title: Phase 9 UI module map
kind: modules
status: active
summary: Human-facing REST surface, stdlib HTTP adapter, lightweight static frontend and the optional Open WebUI shim. Single-container default per §45.1.
sourceRefs:
  - pi_platform/ports/ui/
  - pi_platform/core/ui/
  - pi_platform/adapters/ui/
  - pi_platform/adapters/ui/static/
maintenance:
  mode: authored
---

# Phase 9 UI modules

Phase 9 ships the §57 human interface as three port-and-adapter pairs plus a
single optional adapter for the OpenAI-compatible surface that the Open WebUI
profile consumes.

## Port interfaces (`pi_platform/ports/ui/`)

- `rest_api.py` — `RestApiPort` plus request/response value types declaring
  the ten §44.3 operations (`query`, `retrieve`, `sources`, `graph`, `wiki`,
  `project-version`, `indexing-status`, `knowledge-status`, `materialize`,
  `agent-delegation`). Ports import no implementation module; replacing the
  frontend never requires a change here.

## Core services (`pi_platform/core/ui/`)

- `rest_service.py` — `RestService` composes only existing ports
  (multi-stage retrieval, context assembler, query orchestrator, task
  context, capability discovery, runtime readiness/freshness, graph
  expansion, materialise, policy, egress, trusted approval). `query`
  delegates to the orchestrator; `retrieve` is deterministic retrieval
  only; `project-version` uses the git version-identity seam;
  `indexing-status` and `knowledge-status` derive from runtime readiness
  and freshness; `sources` reports ingestion sources with their source
  policy. `materialize` requires a valid approval token and writes
  nothing otherwise; `agent-delegation` requires an egress decision.

## Adapters (`pi_platform/adapters/ui/`)

- `http_server.py` — stdlib HTTP adapter. Binds loopback by default,
  serves JSON under `/api/v1/*`, serves the static UI, returns 404 for
  unknown routes, optional bearer token from the secret provider, 401
  before any operation when a token is configured and missing/incorrect.
  No third-party imports. Readiness is exposed at `/health/ready`
  separately from `/health` (liveness).
- `composition.py` — composition root. Wires the service from concrete
  platform components. The only place that knows which adapter
  implements which port; the core service depends on ports exclusively.
- `openai_compat.py` — minimal non-streaming OpenAI-compatible shim
  (`GET /v1/models`, `POST /v1/chat/completions`). Disabled unless the
  `open-webui-adapter` feature flag is on; never serves admin/upload
  surfaces.
- `static/` — hand-authored HTML / CSS / vanilla JS. No bundler, no
  `require(`, no `process.env`. References all ten UI operations and
  covers the §57 scenarios.

## Frontend choice

The frontend decision (no Ionic, no Node.js, no npm) is recorded in
ADR 0019. The replacement-by-adapter shape is a direct consequence of
§1, §40 and §57.
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
- `openai_compat.py` — minimal OpenAI-compatible retrieval shim
  (`GET /v1/models`, `POST /v1/chat/completions`). Disabled unless the
  `open-webui-adapter` feature flag is on; never serves admin/upload
  surfaces. The HTTP adapter accepts `stream=true` as finite SSE frames of
  computed retrieval evidence, without calling a chat LLM.
- `static/` — hand-authored HTML / CSS / vanilla JS. No bundler, no
  `require(`, no `process.env`. References all ten UI operations and
  covers the §57 scenarios.

## Frontend choice

The frontend decision (no Ionic, no Node.js, no npm) is recorded in
ADR 0019. The replacement-by-adapter shape is a direct consequence of
§1, §40 and §57.
## Container search repair

The UI reports initialization readiness and polls reindex jobs, including failed
jobs. Its search and Wiki panels render excerpts/page text instead of full JSON.
The managed model selector offers Gemma; a configured native binding is labelled
separately, and retired aliases are absent. The old chat endpoint Save form was
removed because neither it nor PI_OPENAI_BASE_URL connected an upstream model.
Approval and delegation forms are hidden with capability explanations in the
retrieval-only UI. API authentication uses its own field, separate from signed
materialisation approval. Delegation cannot falsely succeed on retrieval alone.

`sources` follows the published runtime inventory, with policy, content hash,
path and source parse failures. Readiness refusals preserve the underlying
failure reason. A manual reindex failure requests a monitor retry even when the
tree has not changed. Busy UI controls prevent duplicate browser clicks.

See [container search repair and upgrade](../../../docs/CONTAINER_SEARCH_REPAIR.md)
for the trade-analyzer topology, local inbox and operator instructions.


## Optional chat and effective execution status

The earlier removal of the browser-only chat fields is superseded by a working
server-side optional chat form. `adapters/orchestration/chat_connection.py` stores
redacted settings in private ignored runtime state and supports bounded
OpenAI-compatible/Anthropic HTTP completion requests. An operator's explicit
context-sharing consent authorizes a short-lived endpoint-scoped approval;
existing egress classification policy and audit remain in the call path.
Retrieval runs first and chat errors fall back to evidence with diagnostics.
The deterministic retrieval operation never calls chat. Open WebUI reuses the
same query behavior. Provider configuration is an admin operation; API keys
are not returned to the browser, and self-recursive endpoints are refused.

`execution_status.py` reports the native model's loaded device or the managed
backend chosen by the deployment overlay. Auto is kept distinct from active
CPU/GPU/Hybrid. Managed GPU + CPU projector is labelled Hybrid as a deployment
profile (not a measured layer count); unknown remote hardware stays Unknown.
See [optional chat and active mode](../../../docs/OPTIONAL_CHAT_AND_EXECUTION_MODE.md).


## Pre-run chat binding

The `chat configure/status/test/disable` CLI reuses `ChatConnection` without
starting HTTP or embeddings. Deployment Make targets wrap it in no-dependency
one-shot containers; explicit `platform-start LLM=1` configures first, `LLM=0`
disables first, and omitted LLM preserves settings. Make forwards provider
variables by name; no key value appears in its command or redacted output.
Pre-run and UI edits share one settings file, so the pre-run URL/model are visible
and editable in the browser. A cache-local ignore rule protects credentials even
when configuration happens before initial hydration/Git exclusion setup.

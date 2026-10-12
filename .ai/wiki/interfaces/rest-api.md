---
id: interfaces.rest-api
title: Phase 9 UI REST interface contract
kind: interfaces
status: active
summary: The §57 UI-facing REST surface. Ten operations, loopback default, bearer token gate, fail-closed materialise and delegation. OpenAPI-style path inventory.
sourceRefs:
  - pi_platform/ports/ui/rest_api.py
  - pi_platform/core/ui/rest_service.py
  - pi_platform/adapters/ui/http_server.py
  - pi_platform/adapters/ui/openai_compat.py
maintenance:
  mode: authored
---

# Phase 9 UI REST interface

The UI surface (REST + static frontend) is the protocol-level contract for
human access. It is defined by `pi_platform/ports/ui/rest_api.py` and served
by the stdlib HTTP adapter in `pi_platform/adapters/ui/http_server.py`.

## Operations (exactly ten, §44.3)

| Method | Path | Operation | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/v1/sources` | `sources` | ingestion source inventory with source policy |
| `GET` | `/api/v1/project-version` | `project-version` | git version identity (§11) |
| `GET` | `/api/v1/indexing-status` | `indexing-status` | runtime readiness + embedding/retrieval status |
| `GET` | `/api/v1/knowledge-status` | `knowledge-status` | freshness/stale/conflict state |
| `POST` | `/api/v1/query` | `query` | orchestrator-routed, may escalate to a local LLM |
| `POST` | `/api/v1/retrieve` | `retrieve` | deterministic retrieval only |
| `POST` | `/api/v1/graph` | `graph` | graph expansion from an entity id |
| `POST` | `/api/v1/wiki` | `wiki` | OKF Wiki read / search |
| `POST` | `/api/v1/materialize` | `materialize` | approval-controlled; writes nothing without a valid token |
| `POST` | `/api/v1/agent-delegation` | `agent-delegation` | egress-controlled; refuses without an ALLOW decision |

The operation set is also returned by capability discovery (§47). Adding
or removing an operation is a breaking interface change.

## Transport

The UI service resolves its repository root before checking approval tokens
or invoking materialisation. Token issuers must use `str(repo_root.resolve())`,
matching the materialiser's canonical repository identity. Exact repository,
action, signature, change-set and expiry checks remain enforced; native Windows
path casing and equivalent path spellings must not create two approval scopes.

- stdlib `ThreadingHTTPServer`; no third-party imports
- loopback bind (`127.0.0.1`) by default
- bearer token gate when `PI_UI_TOKEN` is configured
- 401 before any operation runs when the token is missing/invalid
- 404 for unknown routes; 403 for policy/egress/approval denials
- 503 at `/health/ready` until knowledge hydration completes; `/health`
  returns 200 as soon as the process is alive (liveness)

## Cross-references

- Adapter ownership — `modules.ui`
- §57 / §44.3 / §44.4 in `project-intelligence-platform-architecture-v0.8.md`
- ADR 0018 (REST transport), ADR 0019 (static frontend), ADR 0020 (Open
  WebUI shim)

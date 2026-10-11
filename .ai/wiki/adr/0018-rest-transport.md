---
id: adr.0018-rest-transport
title: Phase 9 REST transport choice
kind: adr
status: accepted
date: 2026-10-11
summary: Phase 9 ships the §57 UI surface on the Python standard library `ThreadingHTTPServer`. Zero new dependencies, loopback default, replaceable adapter. The transport decision is captured so future maintainers do not import a framework.
related:
  - adr.0004-ports-and-adapters-extension-style
  - adr.0011-agent-integration-packaging
  - interfaces.rest-api
  - modules.ui
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#57-human-interfaces
  - openspec/specs/2026-10-11-human-interface-web-ui/spec.md
  - pi_platform/adapters/ui/http_server.py
maintenance:
  mode: authored
---

# ADR 0018 — Phase 9 REST transport choice

## Context

Phase 9 must expose the §57 human interface as a stable, replaceable
adapter over HTTP. The platform already commits to staying
Python-licensed / standards-only at the runtime boundary (ADR 0005). Adding
FastAPI, Flask or any equivalent would import a new third-party
dependency into the final image, push a permanent supply-chain entry
through `LicenseGate`, and bind the UI surface to one framework's
mental model.

The expected load profile is single-user, local, occasional. The UI
needs to answer simple questions from retrieval and context assembly
without a coding harness (per §44.4). It does not need streaming,
multipart uploads, websockets or any feature that would justify a
framework.

## Decision

Use the Python standard library `ThreadingHTTPServer` as the HTTP
adapter. No new third-party dependency is introduced; no `LicenseGate`
entry is required; loopback binding is the default; bearer-token
authentication is implemented in fewer than ten lines.

The REST adapter lives at
`pi_platform/adapters/ui/http_server.py`. The core service
(`pi_platform/core/ui/rest_service.py`) depends only on existing ports.
The protocol contract is declared in
`pi_platform/ports/ui/rest_api.py`. Replacing the transport requires
adding an alternative adapter that satisfies the same port contract.

## Consequences

- **Pro** — zero new dependencies, no licence-inventory entry,
  loopback-only default, deterministic test surface.
- **Pro** — single-file, single-test-surface adapter; easy to audit.
- **Pro** — the port stays the canonical interface; the adapter is
  replaceable without touching the core.
- **Con** — no streaming response today; adding streaming later
  requires an `wsgi`/`asgi` adapter and a parallel port contract.
- **Con** — `BaseHTTPRequestHandler` lacks request-body size limits
  and built-in CORS; the adapter mitigates by length-checking and
  serving the static UI from the same origin.
- **Neutral** — the agent integration and OpenAI-compatible shim stay
  separate adapters (`adapters/ui/openai_compat.py`) so this decision
  does not constrain the Open WebUI profile.
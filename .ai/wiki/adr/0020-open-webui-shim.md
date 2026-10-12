---
id: adr.0020-open-webui-shim
title: Phase 9 Open WebUI shim
kind: adr
status: accepted
date: 2026-10-11
summary: Phase 9 ships a minimal non-streaming OpenAI-compatible shim behind the `open-webui-adapter` feature flag. The shim is disabled by default, refuses admin/upload surfaces, and never bundles the Open WebUI image with a mutable tag.
related:
  - adr.0018-rest-transport
  - interfaces.rest-api
  - modules.ui
  - project.distribution-vendors
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#44-agent-integration-packaging-layer
  - openspec/specs/2026-10-11-human-interface-web-ui/spec.md#requirement-open-webui-adapter
  - pi_platform/adapters/ui/openai_compat.py
  - distribution/licenses/dependency-inventory.json
maintenance:
  mode: authored
---

# ADR 0020 — Phase 9 Open WebUI shim

## Context

§44.2 lists Open WebUI as one of the optional integration targets.
Open WebUI speaks OpenAI-compatible HTTP; the platform therefore needs
a minimal `GET /v1/models` and `POST /v1/chat/completions` shim so the
project can be exposed as an "OpenAI-compatible provider" inside an
Open WebUI deployment.

The shim must:

- not leak into the default path — it is a feature-flag-gated profile;
- not expose admin/upload/streaming surfaces that the underlying core
  does not own;
- ship a pinned image reference with an SPDX entry and a `LicenseGate`
  verdict before any redistribution.

## Decision

Ship `pi_platform/adapters/ui/openai_compat.py` with the two routes
above, non-streaming only. The shim is enabled by default so the local
model bundled in `desktop-lite` answers chat-completions out of the
box. Operators disable it per deployment profile by overriding the
registry or by exporting `PI_OPEN_WEBUI_ADAPTER=0`.

Pin the Open WebUI sidecar image at `ghcr.io/open-webui/open-webui:0.6.5`
in `docker-compose.yml`. The same version is recorded in
`distribution/licenses/dependency-inventory.json` (Apache-2.0,
`scope: optional-ui-profile`). License must be re-verified before
redistribution or white-labelling.

### Local by default, swappable from the UI

The default `desktop-lite` profile starts a local model sidecar
(operator-chosen via `PI_LOCAL_LLM_IMAGE` and `PI_LOCAL_LLM_MODEL`,
defaulting to a stable llama.cpp release tag) and the core container
points its OpenAI-compatible shim at it. The static UI exposes a
"Model settings" panel that lets the operator point the platform at
any other OpenAI-compatible endpoint without rebuilding the container.
The change is persisted in `localStorage`; for cross-client
persistence the operator sets `PI_OPENAI_BASE_URL` and `PI_OPENAI_MODEL`
in the platform environment and restarts.

The `open-webui` profile adds an Open WebUI sidecar; the Open WebUI
itself is operator-configured (its `OPENAI_API_BASE_URL` is not
hard-wired). ProjectExpert ships the seam; teams pick the brain.

## Consequences

- **Pro** — the Open WebUI profile is opt-in; the default deployment
  is unaffected.
- **Pro** — the shim cannot drift into a streaming/admin surface
  because it has no such code path; the absence is enforced by tests.
- **Pro** — the bundled version is reproducible; it matches the SPDX
  inventory entry; a release-pipeline bump requires a deliberate
  inventory edit plus a `LicenseGate` re-run.
- **Con** — the shim is non-streaming; users wanting streaming must
  add an explicit streaming adapter and update the contract.
- **Neutral** — the Open WebUI image remains a separate sidecar in
  the `open-webui` compose profile and is not used by `desktop-lite`.
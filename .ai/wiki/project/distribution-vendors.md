---
id: project.distribution-vendors
title: Phase 9 distribution vendor inventory
kind: project
status: active
summary: Documented distribution profiles (§58), launchers, container artefacts, OKF profile distribution and how they compose. Single container is the default.
sourceRefs:
  - docker-compose.yml
  - Containerfile
  - .dockerignore
  - .github/workflows/publish-oci-container.yml
  - scripts/project-intelligence.sh
  - scripts/Start-ProjectIntelligence.ps1
  - scripts/LAUNCHERS.md
  - distribution/okf-profile/
maintenance:
  mode: authored
---

# Phase 9 distribution vendors

Phase 9 ships the §58 "download → start → open browser" experience and
documents every bundled image, launcher entry point and distribution artefact.

## Documented profiles

| Profile | Composition | Use |
| --- | --- | --- |
| `core-headless` | core container only | CI, headless control-plane access; no model is started |
| `desktop-lite` | core + bundled local-llm sidecar, target repo bound | default "download → start → open browser" (§58) |
| `desktop-local-ai` | desktop-lite + a heavier local model (operator picks runtime + weights) | heavier local inference |
| `open-webui` | desktop-lite + open-webui sidecar | optional Open WebUI profile; chat model is operator-supplied |
| `enterprise` | core + `enterprise-sidecar` placeholder | reserved for Phase 10+ distribution work |

`desktop-lite` is **single-container-with-local-model** in Phase 9. The
Phase 1 `desktop-ui` sidecar was removed because the static UI is now
served by the core image itself (recorded as a Phase 1 contract reversal
in the change's `design.md`). The `local-llm` sidecar is started
alongside the core container so text retrieval answers queries out of
the box; the static UI's "Model settings" panel lets operators swap
the endpoint to any other OpenAI-compatible service without rebuilding
the container.

## Launchers

- `scripts/project-intelligence.sh` — bash launcher for Linux / macOS / WSL.
  Duty list declared in the `DUTIES:` header. `bash -n` clean.
- `scripts/Start-ProjectIntelligence.ps1` — PowerShell launcher for
  Windows PowerShell 5.1+. Same duty list; `Start-Process` browser
  opening. Compiled `.exe` is a release-time artefact only (see
  `scripts/LAUNCHERS.md`).
- The two launchers share one duty set, asserted by the duty-parity test
  in `tests/test_phase_9_launch_smoke.py`.

## Container artefacts

- `Containerfile` — single image; Python 3.11-slim-bookworm base pinned
  by digest; copies `pi_platform/`, `distribution/okf-profile`,
  `distribution/skills`, `distribution/licenses`, `distribution/sbom`,
  and `evals/`; pre-generates the four vendor plugin bundles (`codex`,
  `claude-code`, `opencode`, `generic-agent`) via
  `python -m pi_platform.cli package-plugins`; no Node.js; `EXPOSE 8765`;
  `HEALTHCHECK` for liveness; `CMD ["serve", "--target", "/repo", "--host", "0.0.0.0", "--port", "8765"]`.
- `.dockerignore` — excludes the development harness (`harness.py`,
  `infra/`, `tools/`, `.ai/`, `.agents/`, `openspec/`, `scripts/`) so
  the published OCI container contains only product runtime assets.
- `docker-compose.yml` — five profiles, defaulting `core` and
  `enterprise-sidecar` to
  `${PI_IMAGE:-ghcr.io/shkirmantsev/project-intelligence:dev}` with
  local `Containerfile` build fallback, and every third-party reference
  reproducible (`open-webui: 0.6.5` matches the SPDX dependency-inventory
  entry; `llama.cpp` pinned via `${PI_LOCAL_LLM_IMAGE:-ghcr.io/ggml-org/llama.cpp:b3855}`). No
  mutable `:main` / `:latest` / `:server` tags.
- `.github/workflows/publish-oci-container.yml` — GitHub Actions
  pipeline triggered when a feature branch merges or pushes to `dev` /
  `development` (and on PRs targeting `dev` / `development`). Runs
  product-only verification gates, builds the OCI image, smoke-tests
  readiness, UI, REST API, and MCP `/mcp` against a mounted target
  repository, and publishes `ghcr.io/<owner>/project-intelligence` tags
  (`:dev`, `:development`, `:sha-<commit>`).

## OKF profile distribution

`distribution/okf-profile/` ships the OKF v0.2 compatibility profile
descriptor and a minimal conforming template bundle. Project Wiki
content is **never** bundled into the image; only the profile and
template are copied at build time. Validation runs in the
materialisation path (see `modules.sync`).

## License gating

Every bundled third-party image reference must carry an SPDX entry and
a `LicenseGate` verdict before it may ship. The Open WebUI 0.6.5 entry
in `distribution/licenses/dependency-inventory.json` records the
current shipping version; the license must be re-verified before any
redistribution or white-labelling.

## Cross-references

- ADR 0018 (REST transport), ADR 0019 (static frontend), ADR 0020 (Open
  WebUI shim)
- `modules.ui` for the in-process module map
- `openspec/specs/2026-10-11-one-click-distribution/spec.md`
# Tasks — implement-phase-9-distribution

Implements the three capability specs proposed by
[`prepare-phase-9-distribution`](../prepare-phase-9-distribution/tasks.md) and
mirrors plan tasks 109-116 of
[`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md).

Every task lists the files it owns and a mechanically checkable acceptance
criterion. Tests are `unittest` modules run in isolation. No new Python
third-party dependency is permitted.

## Block A — REST API surface (plan 109)

- [ ] A1 `pi_platform/ports/ui/__init__.py`, `pi_platform/ports/ui/rest_api.py`:
      `RestApiPort` plus request/response value types declaring exactly the ten
      §44.3 operations. Ports import no implementation module.
- [ ] A2 `pi_platform/core/ui/__init__.py`, `pi_platform/core/ui/rest_service.py`:
      `RestService` composed only from existing ports
      (multi-stage retrieval, context assembler, query orchestrator, task
      context, capability discovery, runtime readiness/freshness, graph
      expansion, materialise, policy, egress, trusted approval).
      `query` delegates to the orchestrator; `retrieve` is deterministic
      retrieval only; `project-version` uses git version identity;
      `indexing-status` and `knowledge-status` derive from the runtime
      readiness and freshness seams; `sources` reports ingestion sources with
      their source policy.
- [ ] A3 Fail-closed composition: `materialize` without a valid approval token
      returns HTTP 403 and writes nothing; `agent-delegation` without an ALLOW
      egress decision is refused and performs no outbound call; unknown policy
      action is DENY.
- [ ] A4 `pi_platform/adapters/ui/__init__.py`,
      `pi_platform/adapters/ui/http_server.py`: stdlib HTTP adapter, binds
      loopback by default, serves JSON under `/api/v1/*`, serves the static UI,
      returns 404 for unknown routes, optional bearer token from the secret
      provider, 401 before any operation when a token is configured and
      missing/incorrect. No third-party imports in the module.
- [ ] A5 `pi_platform/cli/main.py`: add `serve` (host/port/target flags) and make
      `health` report liveness plus a distinct readiness result reflecting
      hydration completion.
- [ ] A6 Tests in `tests/test_phase_9_distribution.py`: port declares exactly
      ten operations; core imports no HTTP adapter; policy/egress/approval
      negatives; loopback default; bearer token accept/reject; 404; readiness
      before and after hydrate.
- [ ] A7 Verify: `python -m unittest tests.test_phase_9_distribution` OK and
      `python -m unittest tests.test_architecture` still OK.

## Block B — Lightweight frontend (plan 110)

- [ ] B1 Static assets under `pi_platform/adapters/ui/static/`
      (`index.html`, `app.js`, `styles.css`): vanilla HTML/CSS/JS, no bundler,
      no `require(`, no `process.env`.
- [ ] B2 The frontend references all ten UI operations and covers the §57
      scenarios: ask a question, inspect evidence, browse sources, navigate the
      graph, browse the Wiki, view project version, view indexing status, view
      knowledge status, request materialisation with an approval token, and
      request agent delegation.
- [ ] B3 Served by the core container from the same origin; `GET /` returns HTML,
      static assets resolve, missing assets return 404.
- [ ] B4 Documented equivalence decision (no Node.js at runtime) recorded in
      `design.md` and in ADR 0019.

## Block C — Open WebUI adapter (plan 111)

- [ ] C1 Register the `open-webui-adapter` feature flag in
      `pi_platform/core/control/flags.py`, default OFF.
- [ ] C2 `pi_platform/adapters/ui/openai_compat.py`: minimal non-streaming shim
      `GET /v1/models` and `POST /v1/chat/completions` delegating to the query
      orchestrator. When the flag is off, the routes are not served.
- [ ] C3 Record the pinned Open WebUI version with an SPDX identifier in
      `distribution/licenses/dependency-inventory.json` and a license-gate
      verdict; replace the mutable `:main` tag in `docker-compose.yml`.
- [ ] C4 Tests: flag off by default; shim disabled when off; chat completion maps
      to the orchestrator; no streaming/admin/upload surface exists.

## Block D — OKF profile distribution (plan 112)

- [ ] D1 `pi_platform/core/sync/materialise.py`: run OKF validation before any
      durable commit; an invalid bundle aborts the commit and leaves canonical
      knowledge unchanged.
- [ ] D2 `distribution/okf-profile/`: profile descriptor, validator wiring and a
      template bundle. The image ships the profile and template only — never
      project Wiki content.
- [ ] D3 Fixtures: a conforming OKF v0.2 bundle and invalid variants (missing
      `type`, bad root `okf_version`, missing root declaration, binary runtime
      artefact inside the bundle, reserved `index.md`/`log.md` without `type`).
- [ ] D4 Tests: valid bundle validates; each invalid variant fails with the
      specific violation; reserved files accepted; `pi_` extension field shape
      enforced; `cli okf-validate` exits non-zero on an invalid bundle and zero on
      a valid one.
- [ ] D5 `.ai/wiki` is explicitly out of scope for OKF validation: no existing
      harness Wiki document is rewritten to add an OKF `type`.

## Block E — One-click launchers (plan 113)

- [ ] E1 `scripts/project-intelligence.sh`: verify runtime, export
      `PI_TARGET_REPO`/ports, create volumes, mount the repository, start the
      profile, wait for readiness (not liveness), open the browser when an opener
      exists, print URL and status. `bash -n` clean.
- [ ] E2 `scripts/Start-ProjectIntelligence.ps1`: the same duty list for Windows,
      including `Start-Process` browser opening.
- [ ] E3 Duty-parity test comparing the declared duty sets of both launchers.
- [ ] E4 Documented Windows entry point and how a compiled `.exe` would be
      produced and licensed (release-time artefact, not a committed binary).

## Block F — Image and compose finalisation (plan 114)

- [ ] F1 `Containerfile`: copy the static UI and `distribution/okf-profile`,
      keep the base image pinned by digest, keep liveness `HEALTHCHECK`, expose
      the control/UI port, no Node.js in the final image.
- [ ] F2 `docker-compose.yml`: `desktop-lite` is a single container serving the
      UI; the Phase 1 `desktop-ui` sidecar is removed from the default path;
      `core-headless`, `desktop-local-ai`, `open-webui`, `enterprise` remain
      documented and optional; every bundled image pinned.
- [ ] F3 Tests: compose profile matrix matches §45.3; `PI_MODE` is either
      honoured by `serve` or removed; compose env contract asserted.

## Block G — Launch smoke tests (plan 115)

- [ ] G1 `tests/test_phase_9_launch_smoke.py` in-process part: boot the server
      on an ephemeral port against a small synthetic project fixture and assert
      health, query, sources, project-version and the UI root.
- [ ] G2 Container part: gated by an environment flag and skipped when no
      container runtime exists. Asserts the image builds, the container reaches a
      healthy state, hydrates the synthetic project, serves the UI port and
      answers health.
- [ ] G3 Default offline suite stays deterministic: with the gate disabled the
      suite skips the container part and the whole suite passes.

## Block H — Knowledge, adoption and archive (plan 116)

- [ ] H1 Wiki nodes `modules/ui`, `interfaces/rest-api`,
      `project/distribution-vendors` with stable frontmatter; `INDEX.md` links
      resolve; navigation tests green.
- [ ] H2 ADR 0018 (REST transport), ADR 0019 (static frontend equivalence),
      ADR 0020 (Open WebUI shim).
- [ ] H3 Adopt the three specs under `openspec/specs/2026-10-11-*/` and list each
      exactly once in `openspec/CURRENT.md`.
- [ ] H4 Mark plan tasks 109-116 `[x]`; archive both changes under their archive
      date.
- [ ] H5 `python harness.py check` PASS; `openspec validate --all --strict` PASS;
      full offline suite green; artifact manifest regenerated.
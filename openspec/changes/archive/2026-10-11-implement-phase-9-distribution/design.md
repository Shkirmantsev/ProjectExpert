# Design — prepare-phase-9-distribution

## Scope

This change specifies Phase 9 behaviour only. It ships zero production code.
The following `implement-phase-9-distribution` change implements these deltas.

## Affected architecture

```text
Browser
   ↓  HTTP (REST adapter)
pi_platform/adapters/ui/http_server.py        # stdlib http.server, loopback, bearer token
   ↓  JSON DTO
pi_platform/core/ui/rest_service.py           # operation dispatch + policy + approval + egress
   ↓  ports only
ports/retrieval · ports/orchestration · ports/runtime · ports/control · ports/security
   ↓
Canonical knowledge + runtime store
```

The REST layer is an adapter in the §57 sense. `core/` never imports
`adapters/ui`, so the frontend stays replaceable.

## Operation mapping

| UI operation | Backing seam | Source |
|---|---|---|
| `query` | `QueryOrchestratorPort` | §36 `project.search` / `project.retrieve_context` |
| `retrieve` | `MultiStageRetrievalPort` + `ContextAssemblerPort` | §36 `project.retrieve_context` |
| `sources` | ingestion source inventory with source policy | §8/§9 |
| `graph` | `GraphExpansionPort` + `RuntimeStorePort` | §31 |
| `wiki` | wiki document read/search | §3.3 |
| `project-version` | git version identity | §11 |
| `indexing-status` | runtime readiness + embedding/retrieval status | §62 |
| `knowledge-status` | freshness/stale/conflict state | §55 |
| `materialize` | materialise service behind trusted approval | §48, §8.3 |
| `agent-delegation` | `QueryOrchestratorPort` delegation + `EgressDecisionPort` | §34, §56 |

`query` and `retrieve` intentionally differ: `query` may escalate to the local
LLM or an external agent, `retrieve` is deterministic retrieval only.

## Security composition

Every operation passes three gates in order:

1. **Authentication** — bearer token when a UI token is configured.
2. **Authorisation** — central policy engine, action `ui.<operation>`,
   deny by default for unknown actions.
3. **Capability gates** — `materialize` requires a valid approval token and
   writes nothing otherwise; `agent-delegation` requires an egress decision.

The default composition is fail-closed: no approval provider means no
materialisation, and no egress decision means no outbound call.

## Transport choice

Python standard library `ThreadingHTTPServer`. Rationale: zero new dependencies,
so no license inventory entry is required; loopback-only default; sufficient for
a single-user local control-plane UI. A framework would add a permanent supply
chain dependency for a surface that is explicitly replaceable.

## Frontend choice

The task names "default Ionic or documented equivalent". Phase 9 ships
**hand-authored static assets** — HTML, CSS and vanilla JavaScript served by the
core container — and records the equivalence decision in an ADR. Rationale: no
Node.js or npm dependency in the image, no npm license inventory, no build
stage, and the UI stays replaceable. This is a documented deviation from the
named default and is therefore an ADR, not a silent choice.

The frontend consumes only the ten documented operations.

## Open WebUI integration

Open WebUI speaks OpenAI-compatible HTTP. The profile therefore needs a minimal
non-streaming shim: `GET /v1/models` and `POST /v1/chat/completions`, both
delegating to the query orchestrator. The shim is disabled unless the
`open-webui-adapter` feature flag is on, and the bundled image version must carry
an SPDX entry and a license-gate verdict before it may ship.

## OKF distribution scope correction

Task 112 as written says "package OKF bundle into the container". Shipping
*project* Wiki content in the image would freeze knowledge at build time and fork
the source of truth, which contradicts §68 invariants 1-2 and the mounted-repository
model. Phase 9 therefore ships the **OKF profile adapter, validator and a template
bundle**, and enforces validation in the materialisation path. Project Wiki
content stays in the mounted repository.

`.ai/wiki/` is harness knowledge, not an OKF bundle: its frontmatter uses
`title`/`kind`/`status` and has no OKF `type`. It is explicitly out of scope for
OKF validation and is not rewritten.

## Phase 1 contract reversal

The Phase 1 `docker-compose.yml` listed a `desktop-ui` sidecar in the
`desktop-lite`, `desktop-local-ai` and `open-webui` profiles, duplicating
the core image just to serve static assets. Phase 9 collapses that
sidecar: the lightweight UI is served by the core container at `GET /`,
so `desktop-lite` becomes a single-container profile (§45.1). This is
a deliberate Phase 1 contract reversal and is reflected in:

- `docker-compose.yml` — `desktop-ui` service removed; the static UI is
  copied into the core image at `Containerfile` build time
- `Containerfile` — `COPY pi_platform ./pi_platform` includes
  `pi_platform/adapters/ui/static/`
- the launcher — `start-profile` no longer waits on a second container;
  readiness is checked at `http://localhost:${PI_CONTROL_PORT}/health/ready`
  on the single container
- this ADR — recorded as a contract reversal, not a silent breaking change

The reversal does not affect any agent integration contract. The MCP
server, the agent skill and the OpenAPI admin surfaces all live inside the
single core image.

## Deployment model

- Default: one container serving backend, REST, UI and MCP.
- The Phase 1 `desktop-ui` sidecar in `desktop-lite` contradicts §45.1 and is
  retired; `desktop-lite` becomes a single container.
- The optional second container remains available for the local LLM runtime and
  the Open WebUI profile only.

## Health and readiness

`HEALTHCHECK` stays liveness (`cli health`). Readiness is hydration completion,
surfaced through the readiness seam and the `indexing-status` operation. The
launcher waits for readiness, never for liveness alone.

## Compatibility

- No existing capability is retired. The deltas extend `canonical-knowledge-schema`,
  `plugin-supply-chain-security`, `mcp-server` and `agent-adapter-contract`.
- REST is additive; MCP remains the primary agent interface and is unchanged.
- No new Python dependency, so no runtime compatibility risk.

## Risks

| Risk | Mitigation |
|---|---|
| Materialise endpoint becomes a write bypass | Fail-closed approval; negative test asserts 403 and zero writes |
| Delegation bypasses egress control | Egress decision mandatory in the service layer; negative test |
| UI bundling drags in Node/npm | No-build assets; no npm dependency; ADR records the deviation |
| OKF gate breaks existing materialisation | Gate runs before writes only; existing Phase 1-8 suites must stay green |
| Launchers drift from the image contract | Duty-parity test between Linux and Windows launchers |
| Mutable image tags in compose | Pinned digest/version assertion |
| Container smoke tests make the suite slow or non-deterministic | Gated behind an environment flag; default suite stays offline |

## Alternatives rejected

- **Web framework (FastAPI/Flask):** permanent dependency and license inventory
  cost for a replaceable, loopback-only surface.
- **Ionic/Angular build:** Node toolchain, npm supply chain, larger image.
- **Bundled demo wiki in the image:** contradicts the source-of-truth invariant.
- **Second UI container by default:** contradicts §45.1.
# Proposal — Prepare the v0.8 Phase 9 Distribution Capability Specs

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
requires the platform to be usable **without any coding harness** and to be
installable in a near-zero-setup way: §57 makes human access an independent
first-class interface, §44.3 fixes the UI-facing API surface, §44.4 forbids a
coding-agent dependency, §58 defines the one-click launcher duties, §45.1 makes
a single container the default packaging, §45.3 defines the distribution
profiles, §10 defines the OKF v0.2 portable Wiki profile and §68 fixes the
invariants that distribution must not break.

Phases 1-8 shipped the canonical/runtime split, ingestion, storage, retrieval,
orchestration, MCP + skill distribution, the control plane and the enterprise
security boundary. Nothing yet serves a human: `pi_platform/` has no `ui` port
family, no REST adapter and no static frontend; `Containerfile` is still the
Phase 1 skeleton; `docker-compose.yml` still runs a `desktop-ui` sidecar inside
`desktop-lite`, which contradicts §45.1; and the launchers do not yet implement
the full §58 duty list.

Without Phase 9 the platform has no consumer that is not an AI coding agent, and
the "download → start → open browser" portability goal (§58) is unfulfilled.

## What changes

Three new capability specs are proposed. Nothing in this change is
implemented here; this change ships zero production code.

| Proposed capability | Parent task | Behavioural focus |
|---|---|---|
| `human-interface-web-ui` | 109-111 | Stable UI-facing REST surface, replaceable frontend adapter, no-coding-harness UI, optional Open WebUI profile |
| `okf-wiki-profile-distribution` | 112 | OKF v0.2 validation gate in the materialisation path and a shippable OKF profile adapter |
| `one-click-distribution` | 113-115 | Launcher duties, single-container default image, documented compose profiles, launch smoke verification |

## Affected capabilities

- Extends the accepted `canonical-knowledge-schema` capability, which already
  carries an OKF v0.2 conformance requirement, with an enforced gate in the
  materialisation path.
- Extends the accepted `plugin-supply-chain-security` requirement set with
  pinned-image and license-verdict rules for optional UI distributions.
- Extends the accepted `mcp-server` and `agent-adapter-contract` capabilities by
  stating that REST is an adapter over the same core operations, not a second
  domain model.
- Adds no change to the accepted `enterprise-security-boundary`: the REST
  surface consumes the existing egress policy and policy engine.

## Out of scope

- A2A (`platform.a2a.A2aAdapter`) and reverse delegation hooks — Phase 10.
- Integration quality-gate evaluation suites and the §68 acceptance suite —
  Phase 10, tasks 119-120.
- Any new Python third-party dependency.
- Bundling or redistributing project Wiki content inside the container image.

## Impact

New capability specifications only. The following `implement-phase-9-distribution`
change will ship the REST adapter, the static frontend, the Open WebUI shim, the
OKF gate, the launchers, the finalised image and the Phase 9 regression suite.
# Context impact — prepare-phase-9-distribution

## Knowledge nodes to create (during implementation)

| Node | Content |
|---|---|
| `.ai/wiki/modules/ui.md` | UI API surface, REST adapter, static frontend, Open WebUI shim |
| `.ai/wiki/interfaces/rest-api.md` | Ten documented operations, request/response contracts, auth and error model |
| `.ai/wiki/project/distribution-vendors.md` | Profiles, launchers, image pinning, optional vendors and license verdicts |

`INDEX.md` gains the three links.

## Knowledge nodes to update

| Node | Update |
|---|---|
| `.ai/wiki/architecture/platform-overview.md` | REST/UI enters the data-plane view |
| `.ai/wiki/architecture/system-overview.md` | Distribution and human interface components |
| `.ai/wiki/project/project-map.md` | `pi_platform/{ports,core,adapters}/ui`, `tests/test_phase_9_*` |
| `.ai/wiki/project/implementation-roadmap.md` | Phase 9 status |
| `README.md` | Phase 9 status once shipped |
| `docs/README.md` | Distribution documentation links |

## ADRs to create

| ADR | Decision |
|---|---|
| 0018 | REST transport is the Python standard library HTTP server, loopback-only, optional bearer token |
| 0019 | Frontend is hand-authored static assets — the documented equivalent of the named Ionic default |
| 0020 | Open WebUI integration is a minimal feature-flagged OpenAI-compatible shim; no streaming, no bundling of project knowledge |

ADR 0018 and 0019 are required. ADR 0020 is required because it introduces a new
public protocol surface not present in §44.3.

## Implementation areas

- New: `pi_platform/ports/ui/`, `pi_platform/core/ui/`, `pi_platform/adapters/ui/`
- New: `tests/test_phase_9_distribution.py`, `tests/test_phase_9_launch_smoke.py`,
  OKF fixtures
- Changed: `pi_platform/cli/main.py` (`serve`, health readiness),
  `pi_platform/core/sync/materialise.py` (OKF gate),
  `pi_platform/core/control/flags.py` (Open WebUI flag),
  `Containerfile`, `docker-compose.yml`,
  `scripts/project-intelligence.sh`, `scripts/Start-ProjectIntelligence.ps1`
- New distribution assets: `distribution/okf-profile/`

## Invariants that must not break

- §68.1-2: the mounted Git repository stays the source of truth; no knowledge is
  frozen into the image.
- §68.26: every outbound call passes the egress decision.
- §68.48/§48: materialisation stays approval-controlled and fails closed.
- §68.35/§57: the frontend is replaceable; core does not depend on it.
- §5.5: no dependency ships without an SPDX identifier and a gate verdict.
- §8.4: hydrate/materialise round trip unchanged.

## Verification surface

- `python -m unittest tests.test_phase_9_distribution`
- `python -m unittest tests.test_phase_9_launch_smoke` (container parts gated)
- Full offline suite must stay green (580 tests before Phase 9)
- `python harness.py check`
- `openspec validate --all --strict`
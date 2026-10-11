# Tasks — prepare-phase-8-security

This tasks file mirrors the Phase 8 tasks 105-108 from the
canonical
[`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md).
The tasks below are the future implementation work; they will
be executed by the future `implement-phase-8-security`
change. This change ships zero production code.

The one Phase 8 capability spec under [`specs/`](specs) is
the authoritative behavioural contract for the implementation
work. The future change implements and verifies these
proposed deltas before adoption. Tasks 105-108 remain
unchecked until their implementation and close-out are
verified; preparation completion alone does not adopt or
implement these requirements.

The future `implement-phase-8-security` change depends on:

- the Phase 8 spec being adopted under
  `openspec/specs/2026-10-11-enterprise-security-boundary/`;
- the Phase 7 control plane being adopted
  (`SecretProvider`, `PolicyEngine`, `AuditLog`,
  `Capability` / `Role` vocabulary);
- the Phase 4 retrieval filter
  (`pi_platform/core/retrieval/metadata_filter.py`) being
  in place.

Verification commands referenced below:

- `python -m unittest tests.test_phase_8_security -v` —
  focused regression tests;
- `python -m unittest tests.test_phase_4_retrieval -v` —
  ensures Phase 8 metadata-filter extension preserves
  Phase 4 behaviour;
- `openspec validate --all --strict` — canonical harness
  check;
- `python harness.py check` — configuration / session,
  Wiki, OpenSpec, tests and artifact manifest gate; run
  `license-gate` separately;
- `python harness.py wiki-validate` — Wiki Markdown
  validation;
- `python -m pi_platform.cli license-gate` — license
  inventory gate.

## Phase 8 — Enterprise Security Boundary (preparation only)

### 8.0 — Decision wiring

- [ ] 105.prep. Record the Phase 8 architecture decision as
  `adr/0017-phase-8-enterprise-security-boundary.md` under
  `.ai/wiki/adr/`, status `accepted` upon
  `implement-phase-8-security` start. The ADR MUST cite
  §56 Enterprise Security Boundary, §68.14, §68.26,
  §68.48, §68.50 and MUST link the new ports back to the
  Phase 7 Secret / Policy / Audit foundation.
  → `.ai/wiki/adr/0017-phase-8-enterprise-security-boundary.md`
  (new, by future implement change).
  Verification:
  - the ADR exists and is reachable from
    `.ai/wiki/INDEX.md`;
  - the ADR carries `status: accepted` only after the
    future implement change is adopted.

### 8.1 — Enterprise Boundary implementation (task 105)

- [ ] 105. Implement `EnterpriseBoundary` per the
  [`enterprise-security-boundary`](specs/2026-10-11-enterprise-security-boundary/spec.md)
  capability spec. Ship:

  - `pi_platform/ports/security/boundary.py` (new)
    — `EnterpriseBoundaryPort`;
  - `pi_platform/ports/security/classification.py` (new)
    — `SecurityClassificationPort`,
      `ClassificationLevel`, `SourceClassification`,
      `DocumentClassification`,
      `UnknownClassificationLevelError`;
  - `pi_platform/ports/security/permission.py` (new)
    — `SourcePermissionPort`,
      `SourcePermissionDecision`;
  - `pi_platform/ports/security/detection.py` (new)
    — `SecretDetectorPort`, `SecretFinding`,
      `SecretKind`;
  - `pi_platform/ports/security/egress.py` (new)
    — `EgressDecisionPort`, `EgressRequest`,
      `EgressDecision`;
  - `pi_platform/ports/security/redaction.py` (new)
    — `RedactionPipelinePort`,
      `RedactionFailureError`;
  - `pi_platform/ports/security/audit.py` (new)
    — `SecurityAuditPort`, `SecurityEvent`;
  - `pi_platform/core/security/boundary.py` (new)
    — `DefaultEnterpriseBoundary` (composition root);
  - `pi_platform/core/security/classification.py` (new)
    — `DefaultSecurityClassifier`;
  - `pi_platform/core/security/permission.py` (new)
    — `DefaultSourcePermissionPolicy`;
  - `pi_platform/core/security/detection.py` (new)
    — `DefaultSecretDetector`;
  - `pi_platform/core/security/egress.py` (new)
    — `DefaultEgressPolicy`;
  - `pi_platform/core/security/redaction.py` (new)
    — `DefaultRedactionPipeline`;
  - `pi_platform/core/security/audit.py` (new)
    — `DefaultSecurityAuditRecorder`;
  - `pi_platform/adapters/security/detection_patterns.py`
    (new) — pattern bank;
  - `pi_platform/adapters/security/egress_classifier.py`
    (new) — URL → `127.0.0.1`/`::1`/`localhost` /
    `external` classifier.

  Verification:
  - `python -m unittest tests.test_phase_8_security -v`
    MUST report `OK`;
  - the new ports MUST reject any value outside the
    documented enumeration with a typed error
    (e.g. `UnknownClassificationLevelError`);
  - the `DefaultEgressPolicy` MUST be fail-closed: a
    missing policy engine falls back to `DENY`;
  - the `DefaultSecretDetector` MUST redact finding values
    to `[REDACTED:<kind>]` before placing them in audit
    payloads;
  - the `DefaultRedactionPipeline` MUST raise
    `RedactionFailureError` when the no-resolved-value
    invariant breaks;
  - two consecutive `serialise()` calls on each default
    implementation MUST return byte-identical JSON.

### 8.2 — Retrieval filter integration (task 106)

- [ ] 106. Extend `MetadataFilterCore` per the
  [`enterprise-security-boundary`](specs/2026-10-11-enterprise-security-boundary/spec.md)
  capability spec. The change MUST be additive: a
  `MetadataFilterCore` constructed without
  `enterprise_boundary` MUST behave exactly as it does
  today. The change MUST add the documented
  `security_egress_denied` and `security_redacted`
  reasons and MUST preserve the existing
  `security_denied` reason and drop behaviour.
  → `pi_platform/core/retrieval/metadata_filter.py`
  (extended);
  → `pi_platform/ports/retrieval/metadata_filter.py`
  (extended with the new drop-reason constants).
  Verification:
  - `python -m unittest tests.test_phase_4_retrieval -v`
    MUST continue to report `OK` (no regression);
  - `python -m unittest tests.test_phase_8_security -v`
    MUST report `OK`;
  - the filter constructed with
    `enterprise_boundary=None` MUST produce the same
    statistics as the Phase 4 baseline.

### 8.3 — Regression tests (task 107)

- [ ] 107. Add `tests/test_phase_8_security.py` with
  regression suites for:

  - secret detection (AWS, GitHub, PEM, JWT, high
    entropy);
  - outbound filtering (`localhost ALLOW`,
    `external DENY without capability`,
    `external ALLOW with capability`,
    `external DENY when classification exceeds
    endpoint_allow`);
  - retrieval redaction (coding-agent-read-only redacts
    INTERNAL, redacted chunk carries
    `[REDACTED:INTERNAL]`,
    RedactionFailureError on leak detection);
  - capability-based delegation (actor without
    `secret.reference` denied INTERNAL,
    actor without `network.local` denied external);
  - audit emission (every detector / egress /
    redaction call produces an `AuditRecord`
    with the documented `operation` and
    `resource=[REDACTED:<kind>]` form);
  - failure isolation (a missing policy engine falls
    back to DENY; an Audit Log failure does NOT break
    the calling data-plane path).
  → `tests/test_phase_8_security.py` (new).
  Verification:
  - `python -m unittest tests.test_phase_8_security -v`
    MUST report `OK`;
  - the regression suite MUST include at least 25
    scenarios covering the eight Requirement blocks
    of the spec delta.

### 8.4 — Closeout (task 108)

- [ ] 108. Update the Wiki, archive the change, update
  `openspec/CURRENT.md`, run the harness gate.

  Author / update:

  - `.ai/wiki/modules/security.md` (new) — Phase 8
    Enterprise Security Boundary module map covering
    the §56 vocabulary, the `DefaultEnterpriseBoundary`
    composition root and the relationship to Phase 7
    Secret / Policy / Audit;
  - `.ai/wiki/interfaces/egress.md` (new) — `EgressDecisionPort`,
    `EgressRequest`, `EgressDecision` and the
    default `EgressPolicy`;
  - `.ai/wiki/interfaces/capabilities.md` (update) —
    extend the §59.4 / §59.5 vocabulary section with the
    Phase 8 `network.local` / `network.external`
    cross-reference;
  - `.ai/wiki/modules/policy-engine.md` (update) —
    note that Phase 8 reuses the Phase 7 Policy Engine
    for egress authorisation;
  - `.ai/wiki/modules/secret-provider.md` (update) —
    note that Phase 8 `RedactionPipeline` composes the
    Phase 7 Secret Provider;
  - `.ai/wiki/glossary/platform.md` (extend) — add
    `EgressPolicy`, `SecretDetection`, `SourcePermission`,
    `SecurityClassification`, `RedactionPipeline`;
  - `.ai/wiki/INDEX.md` (update) — add the new entries
    and cross-links; keep the index navigational;
  - `.ai/wiki/architecture/system-overview.md` (update)
    — cite §56 and the accepted
    `enterprise-security-boundary` capability.

  Workflow:

  - `openspec validate prepare-phase-8-security --type
    change --strict` (prepare) MUST pass before
    archive;
  - `openspec validate implement-phase-8-security --type
    change --strict` (future implement) MUST pass
    before archive;
  - `openspec validate --all --strict` MUST pass;
  - the Phase 8 tasks 105-108 in
    `openspec/changes/plan-v0-8-platform-architecture/tasks.md`
    MUST be flipped to `[x]` after the future implement
    change is adopted;
  - `openspec/CURRENT.md` MUST be updated to list the
    one new accepted capability;
  - the future implement change MUST be archived under
    `openspec/changes/archive/YYYY-MM-DD-implement-phase-8-security/`
    on the date of archiving;
  - `python harness.py check` MUST pass.

# Design — prepare-phase-8-security

## Current state

The repository currently contains:

- the development harness framework (`harness.py`,
  `Makefile`, `scripts/`, `.agents/skills/`, `openspec/`,
  `.ai/`, `tools/mcp/`, `.opencode/`, `.claude/`,
  `.codex/`);
- the v0.8 architecture baseline document at the repository
  root
  (`project-intelligence-platform-architecture-v0.8.md`);
- accepted harness and product capabilities
  (`openspec/specs/2026-09-07-*`,
  `openspec/specs/2026-10-03-*`,
  `openspec/specs/2026-10-04-*`,
  `openspec/specs/2026-10-05-*`,
  `openspec/specs/2026-10-07-*`,
  `openspec/specs/2026-10-08-*`);
- the Phase 7 control plane modules under
  `pi_platform/{ports,core,adapters}/control/` (registry,
  hooks, policy, secrets, audit, flags, ui_extensions);
- the Phase 4 retrieval filter
  (`pi_platform/core/retrieval/metadata_filter.py`) that
  already drops hits with the `security_denied` reason
  when the hit's classification is not in the
  `MetadataFilter.securityClassifications` allow-list
  (default `PUBLIC` for unlabelled hits);
- the Phase 6 MCP server
  (`pi_platform/mcp/server.py`) that invokes outbound HTTP
  through the configured transport and routes responses
  through the Phase 7 Secret Provider;
- the existing Wiki nodes documenting the platform
  overview, the implementation roadmap, the Phase 6 / 7
  readiness reviews and the Phase 6 / 7 interface
  contracts;
- the accepted ADRs for the architectural style, the
  canonical / runtime separation, the license governance
  default, the ports-and-adapters extension style, the
  platform source language, Phase 6 / Phase 7 packaging,
  compatibility handshake and plugin supply-chain
  security gates.

The repository does **not** yet contain:

- any `pi_platform/security/` module;
- any `EgressDecisionPort`, `SecretDetectorPort`,
  `SourcePermissionPort`, `RedactionPipelinePort` or
  `SecurityClassificationPort`;
- any documented extension to the Phase 4 metadata filter
  beyond the single `security_denied` drop reason;
- any typed Security Classification vocabulary beyond the
  freeform string field on `MetadataFilter`;
- any documented egress policy for outbound MCP / A2A /
  REST traffic;
- any product Wiki nodes under `modules/security.md` or
  `interfaces/egress.md`.

The Phase 7 Secret Provider resolves the `secret://` and
`env://` reference vocabulary, redacts resolved values in
MCP / A2A / audit / LLM context, and is the Phase 8 input.

## Proposed design

This design covers two scopes:

1. the overall Phase 8 architecture (target end-state),
   used to align the future
   `implement-phase-8-security` change with the same
   vocabulary, module boundaries and dependency rules;
2. the Phase 8 technical design (the implementation
   roadmap) that the future code-producing change will
   execute against, derived from the one Phase 8
   capability spec introduced by this change.

The design is described as module boundaries, runtime
flows, data contracts, technology choices and rules rather
than as finished code.

### Architectural style

The platform adopts the architectural style mandated by
§59 and already used by Phase 7:

- **Hexagonal / Ports-and-Adapters core.** Business logic
  depends on ports; adapters implement ports for specific
  technologies (a Secret detector regex-set adapter, an
  egress URL classifier adapter, a classification default
  adapter, a redaction pipeline adapter).
- **Micro-kernel / Plugin extension surface.** Optional
  capabilities are registered through stable extension
  APIs and never coupled to the core domain; Phase 8
  defines `SecretDetectorPort`, `EgressDecisionPort`,
  `SecurityClassificationPort`, `SourcePermissionPort`,
  `RedactionPipelinePort` as stable extension points.
- **Single modular deployable.** The default deployable is
  one process; the default distribution is one container.
  Phase 8 does not introduce a new deployment unit.

Vendor-specific configuration is excluded from the domain
core. The core remains agent-neutral, model-neutral,
storage-neutral at the architectural level, and
UI-neutral.

### Control plane and data plane

Phase 8 separates its responsibilities across the existing
Phase 7 split:

- **Control plane** — classification defaults, egress
  policy configuration, source permission grants and
  redaction pipeline composition all live under
  `platform.security.*` and are admin-managed through
  the existing Phase 7 control plane (`registry`,
  `policy`, `secrets`, `audit`, `flags`).
- **Data plane** — every retrieval, every outbound MCP /
  A2A / REST call, every chunk serialisation flows
  through the new `RedactionPipelinePort` and the new
  `EgressDecisionPort`; every Phase 4 metadata filter
  call consults the new classification ceiling and source
  permission.

Both planes call into the same central Phase 7 Policy
Engine for any authorisation decision and the same Phase 7
Audit Log for any audit record.

### Modules and packages

The Phase 8 implementation defines the following top-level
product module. The path layout mirrors §64 and the
existing Phase 7 layout.

```text
pi_platform/
├── core/security/
│   ├── boundary.py        # DefaultEnterpriseBoundary (composition root)
│   ├── classification.py  # DefaultSecurityClassifier + ClassificationLevel
│   ├── detection.py       # DefaultSecretDetector + SecretFinding
│   ├── egress.py          # DefaultEgressPolicy + EgressRequest
│   ├── redaction.py       # DefaultRedactionPipeline
│   └── audit.py           # SecurityAuditRecorder (helper over AuditLog)
├── ports/security/
│   ├── boundary.py        # EnterpriseBoundaryPort
│   ├── classification.py  # SecurityClassificationPort + ClassificationLevel
│   ├── detection.py       # SecretDetectorPort + SecretFinding
│   ├── egress.py          # EgressDecisionPort + EgressDecision
│   ├── redaction.py       # RedactionPipelinePort
│   └── permission.py      # SourcePermissionPort + SourcePermission
├── adapters/security/
│   ├── detection_patterns.py  # regex + entropy pattern bank
│   └── egress_classifier.py   # localhost / IP / allow-list classifier
```

`tests/test_phase_8_security.py` verifies the ports and
their default implementations.

The Phase 4 `MetadataFilterCore` is extended in-place to
consult `SecurityClassifier` and `SourcePermissionPort`;
the existing `security_denied` reason is preserved.

### Module: `pi_platform/core/security/boundary`

Implements the `enterprise-security-boundary` composition
root. Responsibilities:

- expose a typed `EnterpriseBoundary` object that holds the
  five ports the Phase 8 spec requires
  (`SecurityClassificationPort`,
  `SourcePermissionPort`, `EgressDecisionPort`,
  `SecretDetectorPort`, `RedactionPipelinePort`);
- wire the Phase 7 `SecretProviderPort`,
  `PolicyEnginePort` and `AuditLogPort` through the
  composition root so the new ports can re-use them;
- expose `evaluate_egress(request)` that composes the
  policy engine authorisation, the classification filter
  and the localhost check into a single `EgressDecision`;
- expose `redact_for(channel, value, classification)` that
  delegates to the `RedactionPipelinePort` and verifies
  the no-resolved-value invariant;
- expose `scan_for_secrets(value)` that runs the detector
  and emits an audit record when findings are reported;
- provide a serialise() that returns a byte-stable
  snapshot of every port's documented state for the
  version compatibility handshake.

### Module: `pi_platform/core/security/classification`

Implements the four-level §56 vocabulary. Responsibilities:

- define the typed `ClassificationLevel` enumeration
  (`PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`)
  with a stable, ordered integral rank used for
  comparison;
- define `SourceClassification(source_id, ceiling)` and
  `DocumentClassification(document_id, level)` typed
  records;
- implement `DefaultSecurityClassifier` that resolves any
  `(source_id, document_id)` to the configured
  classification, with the documented `PUBLIC` fallback;
- serialise the configured source → ceiling mapping in a
  byte-stable order;
- perform no I/O beyond a declared in-memory mapping
  (persistence is the Phase 7 control registry's job).

### Module: `pi_platform/core/security/detection`

Implements the §56 secret detector. Responsibilities:

- expose `SecretFinding(field, value, kind, entropy,
  line_index)` typed records;
- expose a pattern bank under
  `pi_platform/adapters/security/detection_patterns.py`
  with the documented regexes for AWS access keys
  (`AKIA[0-9A-Z]{16}`),
  GitHub personal access tokens (`ghp_[A-Za-z0-9]{36}`),
  PEM private-key headers
  (`-----BEGIN (RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED
  )?PRIVATE KEY-----`),
  and JWT bearer tokens
  (`eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}`);
- compute Shannon entropy over a base64 string of length
  ≥ 40 characters and report a `SecretFinding(kind=entropy,
  entropy=...)` when entropy ≥ 4.5;
- emit an `AuditRecord` through the wired
  `AuditLogPort` for every reported finding; the audit
  payload MUST be redacted (Phase 7 Secret Provider) and
  MUST carry the documented `operation=security.detect`;
- serialise the configured pattern bank in a byte-stable
  order.

### Module: `pi_platform/core/security/egress`

Implements the §56 egress policy. Responsibilities:

- define the typed `EgressRequest(url, classification,
  actor_role, capability_requested)` and
  `EgressDecision(allowed, rationale, channel)` records;
- expose the default `EgressPolicy` that returns
  `EgressDecision(allowed=True, rationale="localhost")`
  when `url` resolves to `127.0.0.1`, `::1` or `localhost`;
- otherwise delegate to the policy engine: the request is
  `ALLOW` only when
  `capability_requested == network.external` AND the
  policy engine approves; the request is `DENY` otherwise
  with a typed rationale;
- emit an `AuditRecord(operation=security.egress)` for
  every evaluation (both ALLOW and DENY) through the
  wired `AuditLogPort`;
- serialise the configured localhost set and decision
  history in a byte-stable order.

### Module: `pi_platform/core/security/redaction`

Implements the §56 redaction pipeline. Responsibilities:

- define the typed `RedactionPipelinePort` with
  `redact(value, *, channel, classification) -> str`;
- implement `DefaultRedactionPipeline` that runs the Phase
  7 `SecretProviderPort.redact` first, then applies a
  classification-driven redaction step (replacing
  `>= INTERNAL` content with `[REDACTED:<LEVEL>]` when
  the consumer's role is `CODING_AGENT_READ_ONLY` or
  `VIEWER`);
- assert the no-resolved-value invariant after the
  pipeline using `SecretProviderPort.has_resolved`; if
  the assertion fails, raise the typed
  `RedactionFailureError`;
- emit an `AuditRecord(operation=security.redact)` for
  every invocation through the wired `AuditLogPort`;
- serialise the pipeline composition
  (`phase7_secret_provider`,
  `phase8_classification_driven`) in a byte-stable order.

### Module: `pi_platform/core/security/audit`

Implements the §56 audit helper. Responsibilities:

- centralise the audit emission helpers used by the
  detection / egress / redaction modules
  (`record_security_event(audit_log, **fields)`);
- enforce the no-secret invariant by routing every
  payload through the Phase 7 redaction filter before
  delegating to the Audit Log;
- provide a typed `SecurityAuditPort` that wraps the
  Phase 7 `AuditLogPort` with the documented
  `operation` vocabulary
  (`security.detect`, `security.classify`,
  `security.egress`, `security.redact`, `security.audit`).

### Module: `pi_platform/core/retrieval/metadata_filter`

Phase 8 extension (in-place). Responsibilities:

- accept an optional `enterprise_boundary:
  EnterpriseBoundaryPort` parameter in the constructor;
- when supplied, consult the boundary for the
  classification ceiling and source permission; preserve
  the existing `security_denied` reason;
- emit the new `security_egress_denied` reason when the
  boundary denies the candidate because the consumer role
  cannot reach the source classification;
- emit the new `security_redacted` reason when the
  boundary redacts but does not drop a candidate (the
  retriever MUST keep the candidate but the context
  assembler MUST replace the textual content with
  `[REDACTED:<LEVEL>]`).

### Concurrency and consistency

- Classification, detection, egress and redaction are pure
  functions of the configured policy and the request
  inputs; they introduce no new locks.
- Audit emission goes through the existing Phase 7
  `AuditLogPort` best-effort shim, so an Audit Log
  failure MUST NOT break the data-plane path.
- The metadata filter remains stateless and thread-safe
  per the Phase 4 contract; the new enterprise-boundary
  parameter is read-only after construction.

### Failure modes and recovery

- Egress DENY is fail-closed: a missing or non-functional
  policy engine returns DENY, never an exception.
- Re-pipeline `RedactionFailureError` is propagated to
  the caller as `DENY` at the data-plane boundary.
- A `SecretDetector` failure (regex compile error) is
  recorded as an audit entry with `result=ERROR` and
  propagates as `True` to callers so the upstream
  redaction pipeline can fall back to `[REDACTED]`.

### Interfaces introduced in Phase 8 (placeholder names;
final names during implementation)

```text
pi_platform.ports.security.boundary.EnterpriseBoundaryPort
pi_platform.ports.security.classification.SecurityClassificationPort
pi_platform.ports.security.classification.ClassificationLevel
pi_platform.ports.security.classification.SourceClassification
pi_platform.ports.security.classification.DocumentClassification
pi_platform.ports.security.permission.SourcePermissionPort
pi_platform.ports.security.permission.SourcePermissionDecision
pi_platform.ports.security.detection.SecretDetectorPort
pi_platform.ports.security.detection.SecretFinding
pi_platform.ports.security.detection.SecretKind
pi_platform.ports.security.egress.EgressDecisionPort
pi_platform.ports.security.egress.EgressRequest
pi_platform.ports.security.egress.EgressDecision
pi_platform.ports.security.redaction.RedactionPipelinePort
pi_platform.ports.security.audit.SecurityAuditPort
pi_platform.ports.security.audit.SecurityEvent
```

### Cross-cutting decisions

- Every product module MUST expose ports; adapters live
  under `pi_platform/adapters/security/` and never under
  `pi_platform/core/security/` or `pi_platform/ports/security/`;
- The Phase 8 ports compose the Phase 7 ports; Phase 8
  does not duplicate Phase 7 contracts.
- Classification metadata is canonical under
  `project-knowledge/` per §7.1; the runtime classifier
  is a read-only projection of the canonical mapping.
- The metadata filter's new reasons
  (`security_egress_denied`, `security_redacted`) are
  addition-only; the existing `security_denied` contract
  is preserved.
- All audit records routed through the new
  `SecurityAuditPort` MUST pass the Phase 7 redaction
  filter; the new port is a thin wrapper, not a
  re-implementation.

## Affected modules / interfaces

| Module / path | Affect |
| --- | --- |
| `openspec/changes/prepare-phase-8-security/` | new (this change) |
| `openspec/specs/2026-10-11-enterprise-security-boundary/` | new (after adoption) |
| `openspec/CURRENT.md` | updated to list the one new accepted capability |
| `pi_platform/ports/security/...` (7 new ports) | new (future implement) |
| `pi_platform/core/security/...` (5 new cores) | new (future implement) |
| `pi_platform/adapters/security/...` (2 new adapters) | new (future implement) |
| `pi_platform/core/retrieval/metadata_filter.py` | extended (future implement) |
| `.ai/wiki/modules/security.md` | new (future implement) |
| `.ai/wiki/interfaces/egress.md` | new (future implement) |
| `.ai/wiki/interfaces/capabilities.md` | updated (future implement) |
| `.ai/wiki/modules/policy-engine.md` | updated (future implement) |
| `.ai/wiki/modules/secret-provider.md` | updated (future implement) |
| `.ai/wiki/glossary/platform.md` | extended (future implement) |
| `.ai/wiki/INDEX.md` | updated (future implement) |
| `.ai/wiki/architecture/system-overview.md` | updated (future implement) |
| `.ai/wiki/adr/0017-phase-8-enterprise-security-boundary.md` | new (future implement) |

## Data / persistence / concurrency impact

- Security Classification source mapping lives as
  canonical knowledge under `project-knowledge/security/
  sources.yaml` so the runtime classifier is a
  deterministic projection of the canonical mapping.
- Secret detector pattern bank lives as canonical
  knowledge under `project-knowledge/security/
  detection-patterns.json`.
- Egress localhost set lives as canonical knowledge under
  `project-knowledge/security/egress-localhosts.yaml`.
- None of the canonical knowledge files require a new
  runtime DB migration; Phase 8 ships them as static
  YAML / JSON the runtime loads on hydrate.
- The runtime cache reuses the existing Phase 1 content-
  addressed cache; classification metadata is part of the
  canonical chunk metadata (already produced by Phase 2
  ingestion).
- No additional locks; Phase 8 work is read-mostly with
  audit emission.

## Compatibility and migration

This change introduces only new files and one capability
spec. No existing source, schema, API or contract is
modified.

- No public harness contract changes.
- No OpenSpec schema change (production-sdd schema is
  reused).
- No CLI command changes (the future implement change
  will add new commands; this change does not).
- No backward-compatibility flag needed because no
  consumer exists yet for Phase 8 ports.
- The Phase 4 metadata filter change is additive; the
  existing `security_denied` reason and the existing
  public API remain unchanged.

## Risks and rollback

Risks:

- Adding classification defaults that disagree with an
  existing source would silently upgrade or downgrade
  retrieval. Mitigation: the default is PUBLIC, the
  classifier is opt-in (the filter accepts `None` as
  "no boundary attached") and the enterprise boundary
  preserves every existing drop reason.
- A regex false positive on the secret detector would
  blank an entire chunk. Mitigation: findings are
  recorded as audit events but never silently mutate
  outputs; the redaction pipeline only fires on the
  `RedactionPipelinePort` contract, not on detections
  alone.
- The egress policy must not become a single point of
  failure for the platform. Mitigation: localhost
  requests are evaluated as a pure function of the URL
  before any policy engine call; a missing policy engine
  falls back to DENY (fail-closed, recorded in audit).

Rollback:

- this change reverts cleanly by deleting
  `openspec/changes/prepare-phase-8-security/` and the
  Wiki edits (the future implementation change has not
  yet produced Wiki edits; the Wiki edits live in the
  future change);
- before the future `implement-phase-8-security` change
  is adopted, there is no runtime artifact to roll back.

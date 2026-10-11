# Proposal — Prepare the v0.8 Phase 8 Enterprise Security Boundary Capability Spec

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
defines the **Enterprise Security Boundary** as the eighth
implementation phase (§56, invariant family §68.14 / §68.26 /
§68.48 / §68.50). Phase 8 turns the Phase 7 Secret Provider,
Policy Engine and Audit Log into a production-grade security
envelope that separates **local access** from
**external transmission**: secret detection for transient
values the Secret Provider never resolved, a typed
`SourcePermissionPort` that maps each
`(source_id, target_consumer)` to ALLOW / REDACT / DENY, a
typed `SecurityClassificationPort` with the PUBLIC / INTERNAL /
CONFIDENTIAL / RESTRICTED vocabulary, an `EgressDecisionPort`
that inspects every outbound network call before it leaves the
platform, a `RedactionPipelinePort` that composes Secret
Provider redaction with classification-driven redaction, and a
mandatory audit record for every security-relevant action.

Phase 1 supplies the canonical stores and a
`PolicyDecisionStub` that this phase shares; Phase 4 supplies
the `MetadataFilterCore` that already drops hits with reason
`security_denied`; Phase 6 supplies the MCP server that emits
outbound HTTP calls; Phase 7 supplies the §59 Secret Provider,
§59.4 capability vocabulary, §59.5 role defaults, §59.11
Policy Engine, §59.12 Approval / Denial / Authorize contract
and §59.13 Audit Log that the Enterprise Boundary composes on
top of.

Without Phase 8 specs:

- there is no authoritative behavioural contract for the
  `SecurityClassification` vocabulary beyond the single
  string field the Phase 4 metadata filter accepts, so
  retrieval redaction and egress decisions can diverge;
- the §56 `secret detection`, `source-level permissions`,
  `outbound filtering`, `redaction`, `egress policy` and
  `auditability` capabilities are unspecified;
- the Phase 6 MCP server has no egress policy wrapper, so a
  coding agent with the `mcp.invoke` capability can still
  reach arbitrary external URLs through the configured HTTP
  transport;
- the Phase 4 retrieval filter has no typed way to verify
  that downstream `RETRIEVAL_QUERY` callers receive content
  matching their classification ceiling, so a Viewer could
  ingest RESTRICTED chunks once the upstream SourceAdapter
  mis-classifies them;
- a chunk that carries a raw (non-reference) AWS access key
  pasted into a customer comment can pass through ingestion,
  ingestion never reaches the Secret Provider, and retrieval
  emits the key into every MCP response;
- the existing `security_denied` drop reason is a
  self-contained property of the metadata filter; an operator
  cannot tell whether the drop came from an egress decision,
  a classification ceiling or a source permission.

Phase 9's one-click launcher has no egress policy to bake
into the security smoke tests; Phase 10's A2A adapter has no
centralised egress policy to wrap delegation traffic. This
change authoring gap is the prerequisite for the Phase 8
implementation.

This change resolves the gap by authoring the one Phase 8
capability spec and the supporting design, context-impact
and tasks, while shipping zero production code. The
implementation work is proposed under
`implement-phase-8-security`; its mirrored delta remains a
future requirement until implementation, verification and
adoption. Preparation completion does not adopt this
capability. At adoption, reconcile the provisional
`2026-10-11-enterprise-security-boundary` delta identity in
both changes to the actual first Git acceptance date, then
promote exactly one delta set. Archive preparation without
reapplying its duplicate ADDED requirements.

## Goal

Author the Phase 8 capability spec and change artifacts so
that a later `implement-phase-8-security` change can:

- ship `EnterpriseBoundary` (`platform.security.boundary`)
  as the single composition root that wires the Phase 7
  Secret Provider, the §56 secret detector, the typed
  `SourcePermissionPort`, the `EgressDecisionPort`, the
  `RedactionPipelinePort` and the existing `AuditLogPort`;
- ship `SecurityClassifier` (`platform.security.classification`)
  with the four-level vocabulary (PUBLIC / INTERNAL /
  CONFIDENTIAL / RESTRICTED), the default PUBLIC fallback for
  unlabelled chunks, the typed `ClassificationLevel` and the
  typed `SourceClassification` carrying the per-source
  ceiling;
- ship `SecretDetector` (`platform.security.detection`) that
  scans transient values (chunk text, outgoing payloads,
  audit messages) for the documented high-signal patterns
  (AWS access keys, GitHub tokens, PEM private-key headers,
  JWT bearer tokens, generic base64 strings ≥ 40 characters
  with Shannon entropy ≥ 4.5) and emits typed
  `SecretFinding` records;
- ship `EgressPolicy` (`platform.security.egress`) as the
  default §56 implementation of `EgressDecisionPort` with
  the documented localhost ALLOW, classification-allow-list
  filter, `network.external` capability gate and DENY
  fail-closed behaviour;
- ship `RedactionPipeline` (`platform.security.redaction`)
  that runs the Phase 7 Secret Provider redaction first,
  applies classification-driven redaction
  (`[REDACTED:CONFIDENTIAL]`) second, then asserts the
  `has_resolved` invariant before the pipeline returns;
- extend `MetadataFilterCore` to consult the new
  Enterprise Boundary; preserve the existing
  `security_denied` reason and add the documented
  `security_egress_denied` and `security_redacted` reasons;
- add `tests/test_phase_8_security.py` with regression suites
  for secret detection, outbound filtering, retrieval
  redaction, capability-based delegation and Wiki /
  knowledge evidence.

Out of scope for this change:

- writing any platform source code, container build file,
  OCI artefact, plugin bundle, or any other runtime
  artefact;
- operating the platform against a target project (that is
  a runtime concern of the container bound to a target
  repo, not a concern of this implementation repo);
- replacing or bypassing Phase 7 Secret Provider, Policy
  Engine or Audit Log; the Enterprise Boundary composes
  them.

What this change does:

- proposes the one Phase 8 capability spec
  (`enterprise-security-boundary`) that lands in
  `openspec/specs/2026-10-11-enterprise-security-boundary/`
  upon archive;
- describes the overall architectural design and the
  Phase 8 technical design following the
  hexagonal / ports-and-adapters + micro-kernel style of
  §59;
- enumerates Wiki / ADR nodes to be updated by the future
  `implement-phase-8-security` change;
- enumerates the four Phase 8 tasks (105-108) the future
  implementation change will execute against.

Adoption model (resolves the prepare / implement split):

- **this change IS archivable now** because all its
  acceptance criteria are planning artifacts (one proposal,
  one spec delta, design, context-impact, tasks) and those
  artifacts have been authored, validated by `openspec
  validate --changes` and are internally consistent;
- when this change is archived (via the standard OpenSpec
  archive workflow), the spec delta is promoted to the
  accepted capability folder
  `openspec/specs/2026-10-11-enterprise-security-boundary/`;
- the future `implement-phase-8-security` change depends on
  the accepted capability spec being present in
  `openspec/specs/` and implements exactly the Phase 8 tasks
  (105-108) defined in this change's `tasks.md`;
- the future implementation change also depends on Phase 7
  (`prepare-phase-7-control-plane` /
  `implement-phase-7-control-plane`) being adopted, since it
  composes the Secret Provider, Policy Engine and Audit Log.

## Affected capabilities

### What changes

This change introduces the following additive product
capability spec. No existing capability (harness or product)
is modified or retired by this change.

- `openspec/changes/prepare-phase-8-security/specs/2026-10-11-enterprise-security-boundary/spec.md`
  — additive; new capability; lands in
  `openspec/specs/2026-10-11-enterprise-security-boundary/`
  upon archive.

The capability table below lists every Phase 8 capability
that later OpenSpec changes will introduce after the Phase 7
control plane is adopted; it is listed for end-to-end review
of the v0.8 architecture but produces only this single spec
file in this change.

| New capability | Architecture sections | Phase |
| --- | --- | --- |
| `enterprise-security-boundary` | §56, §68.14, §68.26, §68.48, §68.50 | 8 — Security |

This change ships the **one Phase 8 capability spec**.

The capability table mirrors the canonical Phase 8 row in
[`tasks.md`](../plan-v0-8-platform-architecture/tasks.md#phase-8--security-enterprise-boundary).

`openspec/specs/` currently contains the Phase 1-7 accepted
capability folders (`2026-09-07-*`, `2026-10-03-*`,
`2026-10-04-*`, `2026-10-05-*`, `2026-10-07-*`,
`2026-10-08-*`). This change introduces the first Phase 8
capability under the dated folder convention.

No existing capability is **modified** or **retired** by this
change. No accepted harness or product capability is affected.

## Compatibility / migration impact

This change is a pure planning artifact: no source files, no
runtime configuration, no dependencies, no public contracts,
and no API versions are changed. The only filesystem impact
is the creation of new files under
`openspec/changes/prepare-phase-8-security/`.

Compatibility constraints this plan respects:

- the `production-sdd` OpenSpec schema selected in
  `openspec/config.yaml`; this plan uses the same artifact
  sequence (`proposal → specs → design → context-impact →
  tasks`);
- lowercase kebab-case change ID without date prefix
  (`prepare-phase-8-security`);
- archive folder convention
  `archive/YYYY-MM-DD-original-change-name/` is preserved
  for the future archive step;
- the harness agent contract (`AGENTS.md`,
  `.ai/AGENTS.md`) is followed: Markdown is canonical,
  secrets stay out of the Wiki, generated indexes live
  under `tmp/local/`;
- the existing project Wiki structure (`.ai/wiki/architecture/`,
  `.ai/wiki/project/`, `.ai/wiki/glossary/`,
  `.ai/wiki/adr/`, `.ai/wiki/modules/`,
  `.ai/wiki/interfaces/`) is extended with new durable
  knowledge nodes rather than rewritten;
- the existing harness commands, skill routing and OpenSpec
  layout validation scripts are untouched.

No migration steps are required for downstream consumers
because no public contract changes in this change.

## Related knowledge

- `kb://architecture.system-overview` — high-level
  boundaries; mirrors the v0.8 architecture; to be updated
  by the future `implement-phase-8-security` change to
  reference the new accepted Enterprise Security Boundary
  capability.
- `kb://architecture.platform-overview` — phase table; to be
  updated by the future implementation change to mark
  Phase 8 planned → shipped.
- `kb://project.map` — repository navigation; to be updated
  by the future implementation change to reference the
  `pi_platform/security/` module map and the new
  `interfaces/egress.md` node.
- `kb://project.task-handoff` — durable task-state
  lifecycle; informs the implementation order recorded in
  `tasks.md`.
- `kb://project.implementation-roadmap` — phase table; to
  mark Phase 8 tasks 105-108 as shipped.
- `kb://interfaces.secret-provider` — the Phase 7 port that
  Phase 8 composes; the future implementation change adds
  cross-link from `interfaces/egress.md`.
- `kb://interfaces.policy-engine` — the §59.4 capability
  vocabulary that Phase 8 reuses for egress authorisation.
- `kb://interfaces.audit-log` — the Phase 7 Audit Log that
  Phase 8 emits security-relevant records through.
- `kb://adr.0002-canonical-runtime-separation` — Phase 8
  honours the canonical / runtime split by keeping the
  classification metadata as canonical under
  `project-knowledge/` and using it through the runtime
  filter only.
- `kb://adr.0004-ports-and-adapters-extension-style` —
  Phase 8 strictly follows the ports/adapters split.
- `kb://glossary.platform` — to be extended with the Phase 8
  vocabulary (`EgressPolicy`, `SecretDetection`,
  `SourcePermission`, `SecurityClassification`,
  `RedactionPipeline`).
- external: `project-intelligence-platform-architecture-v0.8.md`
  §56 Enterprise Security Boundary and §68 architectural
  invariants #14 / #26 / #48 / #50 (this change cites the
  sections it introduces the new capability for).

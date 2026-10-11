# enterprise-security-boundary Specification delta

## Purpose

Expose the Enterprise Security Boundary with the four-level
Security Classification vocabulary, the secret detection
extension to the Phase 7 Secret Provider, the typed Source
Permission port, the egress policy that inspects every
outbound network call, the redaction pipeline that composes
Phase 7 redaction with classification-driven redaction, and
the mandatory audit emission for every security-relevant
action.

## Requirements

### Requirement: Security Classification vocabulary

The Enterprise Boundary MUST expose a typed
`SecurityClassificationPort` carrying a four-level
`ClassificationLevel` vocabulary:

```text
PUBLIC          # open knowledge; no constraint
INTERNAL        # project-internal; coding-agent-read-only consumers redact
CONFIDENTIAL    # restricted to maintainers; consumers redact
RESTRICTED      # bounded to administrators; consumers drop when below ceiling
```

Chunks whose classification metadata field is missing MUST
default to `PUBLIC` so a missing field never silently
upgrades a RESTRICTED source. The classifier MUST provide a
stable ordered integral rank (`PUBLIC=0`, `INTERNAL=1`,
`CONFIDENTIAL=2`, `RESTRICTED=3`) used for comparison.

#### Scenario: classifier defaults to PUBLIC for an unlabelled chunk

Given a chunk metadata without a `classification` field
When the classifier resolves the chunk classification
Then the classifier returns `ClassificationLevel.PUBLIC`.

#### Scenario: classifier rejects an unknown level

Given a chunk metadata with `classification = "TOP_SECRET"`
When the classifier resolves the chunk classification
Then the classifier raises
`UnknownClassificationLevelError(level="TOP_SECRET")`.

### Requirement: Secret detection scans transient values

The Enterprise Boundary MUST expose a typed
`SecretDetectorPort` that scans arbitrary string values and
returns one or more `SecretFinding` records when the value
matches any of the documented patterns:

```text
AWS_ACCESS_KEY              = r"AKIA[0-9A-Z]{16}"
GITHUB_TOKEN               = r"ghp_[A-Za-z0-9]{36}"
PEM_PRIVATE_KEY_HEADER     = r"-----BEGIN (RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"
JWT_BEARER                 = r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
GENERIC_API_KEY            = r"(?i)api[-_]?key[\"'`]?\s*[:=]\s*[\"'`]([A-Za-z0-9_\-]{16,})[\"'`]"
HIGH_ENTROPY_BASE64        = shannon_entropy(value) >= 4.5 AND len(value) >= 40 AND no_whitespace(value)
```

Each finding MUST carry `field`, `value`, `kind`,
`entropy` and a `line_index` and MUST be returned through
the standard `scan(value)` entry point. A finding's `value`
MUST be redacted to the documented
`[REDACTED:<kind>]` form before being placed in any audit
payload, log line or external response. The detector
complements the Phase 7 Secret Provider; it does not
replace it.

#### Scenario: detector identifies an AWS access key

Given a chunk text contains the substring `AKIAIOSFODNN7EXAMPLE`
When the detector scans the value
Then the detector returns a `SecretFinding(kind="AWS_ACCESS_KEY")`
And an `AuditRecord(operation=security.detect, result=FOUND)` is
emitted through the wired `AuditLogPort`.

#### Scenario: detector identifies a high-entropy base64 string

Given a chunk text contains a 48-character base64 string with
Shannon entropy `4.91`
When the detector scans the value
Then the detector returns a `SecretFinding(kind="HIGH_ENTROPY_BASE64",
entropy=4.91)`
And an `AuditRecord(operation=security.detect, result=FOUND)` is
emitted through the wired `AuditLogPort`.

#### Scenario: detector returns no findings on a benign string

Given a chunk text contains only the substring
`"The quick brown fox jumps over the lazy dog"`
When the detector scans the value
Then the detector returns an empty list
And no audit record is emitted.

### Requirement: Source-level permissions

The Enterprise Boundary MUST expose a typed
`SourcePermissionPort` that maps every
`(source_id, target_consumer_role)` to one of three
decisions: `ALLOW`, `REDACT` or `DENY`. The default policy
MUST be:

```text
(source, PUBLIC)                           -> ALLOW
(source, INTERNAL)                         -> ALLOW when role != CODING_AGENT_READ_ONLY else REDACT
(source, CONFIDENTIAL)                     -> REDACT for VIEWER / CODING_AGENT_READ_ONLY, ALLOW for MAINTAINER / ADMINISTRATOR
(source, RESTRICTED)                       -> DENY unless role == ADMINISTRATOR
```

The decision MUST be returned through a typed
`SourcePermissionDecision` carrying the resolved decision,
the matching rule and the rationale string. The default
policy is in-memory; persistent configuration lives in the
canonical tree per §7.1.

#### Scenario: coding agent cannot view INTERNAL content

Given a source classified `INTERNAL`
and a `RedactionPipeline` invocation by a
`Role.CODING_AGENT_READ_ONLY` actor
When the source permission port evaluates the request
Then the port returns
`SourcePermissionDecision(decision=REDACT,
rule=coding_agent_internal, rationale="...")`.

#### Scenario: maintainer can view CONFIDENTIAL content

Given a source classified `CONFIDENTIAL`
and a `RedactionPipeline` invocation by a
`Role.MAINTAINER` actor
When the source permission port evaluates the request
Then the port returns
`SourcePermissionDecision(decision=ALLOW,
rule=maintainer_confidential, rationale="...")`.

### Requirement: Egress policy inspects every outbound call

The Enterprise Boundary MUST expose a typed
`EgressDecisionPort` that evaluates an `EgressRequest`
carrying `url`, `classification`, `actor_role` and
`capability_requested`. The default policy MUST be:

```text
url resolves to 127.0.0.1 / ::1 / localhost            -> ALLOW (rationale="localhost")
url otherwise AND capability == network.external AND
   classification <= endpoint_allow                    -> ALLOW
url otherwise                                          -> DENY (rationale=...)
```

The decision MUST be returned as a typed
`EgressDecision(allowed, rationale, channel)`. Every
evaluation (ALLOW or DENY) MUST emit an `AuditRecord` with
`operation=security.egress` and `resource=<resolved URL>`.
The decision MUST be `DENY` (fail-closed) when the policy
engine cannot be consulted.

#### Scenario: localhost ALLOW

Given an `EgressRequest(url="http://127.0.0.1:7777/mcp/invoke",
classification=PUBLIC, capability_requested=mcp.invoke)`
When the egress port evaluates the request
Then the port returns
`EgressDecision(allowed=True, rationale="localhost",
channel=loopback)`.

#### Scenario: external DENY without capability

Given an
`EgressRequest(url="https://example.com/api",
classification=PUBLIC,
capability_requested=mcp.invoke)`
When the egress port evaluates the request
Then the port returns
`EgressDecision(allowed=False,
rationale="network.external capability required",
channel=external)`.

#### Scenario: external ALLOW with capability

Given an
`EgressRequest(url="https://example.com/api",
classification=PUBLIC,
capability_requested=network.external)` and the actor holds
the `network.external` capability
When the egress port evaluates the request
Then the port returns
`EgressDecision(allowed=True,
rationale="capability=network.external and
endpoint_allow contains PUBLIC",
channel=external)`.

#### Scenario: external DENY when classification exceeds endpoint_allow

Given an
`EgressRequest(url="https://example.com/api",
classification=RESTRICTED,
capability_requested=network.external)` and the endpoint
allow-list is `PUBLIC`
When the egress port evaluates the request
Then the port returns
`EgressDecision(allowed=False,
rationale="classification=RESTRICTED not in endpoint_allow=PUBLIC",
channel=external)`.

### Requirement: Redaction pipeline composes Phase 7 Secret Provider and classification-driven redaction

The Enterprise Boundary MUST expose a typed
`RedactionPipelinePort` that returns a redacted copy of a
value through two ordered steps:

```text
1. Phase 7 Secret Provider redact(value, channel=...)
2. Classification-driven redact(value, ceiling=classification, role=actor_role)
```

The classification-driven step MUST replace any chunk whose
classification is `>= INTERNAL` with `[REDACTED:<LEVEL>]`
when the actor role is `CODING_AGENT_READ_ONLY` or `VIEWER`.
The pipeline MUST assert the no-resolved-value invariant
after step 2 by calling
`SecretProvider.has_resolved`; if the assertion fails, the
pipeline MUST raise the typed `RedactionFailureError`.

The pipeline MUST emit an `AuditRecord` with
`operation=security.redact` for every invocation. The
serialised form MUST be byte-stable across consecutive
calls on the same state.

#### Scenario: redaction pipeline redacts a SEC_PROVIDER resolved value

Given the Phase 7 `SecretProvider` has resolved
`env://HTTP_PROXY` to `http://proxy:8080`
and the chunk text contains the resolved value
When the pipeline redacts the chunk
Then the redacted chunk carries
`env://HTTP_PROXY[REDACTED]` instead of `http://proxy:8080`.

#### Scenario: redaction pipeline redacts INTERNAL content for a coding-agent reader

Given a chunk classified `INTERNAL` and the actor role is
`Role.CODING_AGENT_READ_ONLY`
When the pipeline redacts the chunk for the actor
Then the redacted chunk carries `[REDACTED:INTERNAL]`
And an `AuditRecord(operation=security.redact, result=REDACTED)`
is emitted.

#### Scenario: redaction pipeline raises RedactionFailureError on leak

Given the Phase 7 `SecretProvider` has resolved
`env://HTTP_PROXY` to `http://proxy:8080`
and the classification-driven step somehow leaves the
resolved value in place
When the pipeline asserts the no-resolved-value invariant
Then the pipeline raises `RedactionFailureError(reason="leak")`.

### Requirement: Retrieval filter integration

The Phase 4 `MetadataFilterCore` MUST consult the
Enterprise Boundary when the filter is constructed with
an `enterprise_boundary` parameter. The integration MUST:

- preserve the existing `security_denied` reason for hits
  whose classification is not in the caller's allow-list;
- emit a new `security_egress_denied` reason when the
  Enterprise Boundary denies the candidate because the
  consumer role cannot reach the source classification
  for an egress-bound consumer;
- emit a new `security_redacted` reason when the
  Enterprise Boundary redacts but does not drop the
  candidate; the retriever MUST keep the candidate but
  the context assembler MUST replace the textual content
  with `[REDACTED:<LEVEL>]` before serialisation;
- remain additive: a `MetadataFilterCore` constructed
  without `enterprise_boundary` MUST behave exactly as
  it does today.

#### Scenario: filter drops a RESTRICTED hit for a viewer

Given a hit metadata with `securityClassification=RESTRICTED`
and a `MetadataFilter(projectVersion=..., securityClassifications={PUBLIC})`
When the filter applies to the hit list
Then the filter drops the hit with reason `security_denied`
(unchanged from Phase 4).

#### Scenario: filter adds security_redacted for a coding-agent reader

Given a hit metadata with `securityClassification=INTERNAL`
and a `MetadataFilter` constructed with a wired
`EnterpriseBoundary(actor_role=CODING_AGENT_READ_ONLY)`
When the filter applies to the hit list
Then the filter keeps the hit but reports the `security_redacted`
reason in its dropped-by-reason statistics
And the context assembler replaces the hit text with
`[REDACTED:INTERNAL]` before serialisation.

### Requirement: Auditability of security actions

Every security-relevant action MUST emit an `AuditRecord`
through the Phase 7 `AuditLogPort`. The new `operation`
vocabulary is:

```text
security.detect
security.classify
security.egress
security.redact
security.audit
```

The audit payload MUST be redacted through the Phase 7
Secret Provider before it reaches the Audit Log; the
detector finding `value` MUST be replaced by
`[REDACTED:<kind>]`. Audit emission MUST be
best-effort: a failed Audit Log MUST NOT break the calling
data-plane path (matching the Phase 7 audit shim
contract).

#### Scenario: detector emits a redacted audit record

Given a chunk text contains the substring
`AKIAIOSFODNN7EXAMPLE`
When the detector scans the value and the audit log is wired
Then the Audit Log records
`{"operation":"security.detect","result":"FOUND",
"resource":"[REDACTED:AWS_ACCESS_KEY]"}`
And the Audit Log does NOT contain the literal
`AKIAIOSFODNN7EXAMPLE`.

#### Scenario: audit failure does not break the data plane

Given the wired Audit Log raises `SecretLeakageError`
mid-emission
When the detector emits its audit record
Then the data-plane caller still returns a valid finding list
And the detector records an `OperationalLog(level=ERROR)`
entry instead of propagating the exception.

### Requirement: Capability-based delegation through egress

The egress policy MUST integrate with the Phase 7
`PolicyEnginePort`:

- an actor carrying only `network.local` MUST be denied
  every non-localhost URL; the egress response MUST be
  `EgressDecision(allowed=False, rationale="...",
  channel=external)`;
- an actor with `network.external` MUST receive the
  classification / endpoint allow-list decision;
- an actor without `secret.reference` MUST be denied
  every payload whose classification is `>= INTERNAL`.

#### Scenario: actor without secret.reference cannot view INTERNAL

Given an actor carrying `knowledge.read` and
`retrieval.query` only (no `secret.reference`)
When the Enterprise Boundary evaluates a payload for an
INTERNAL chunk
Then the Enterprise Boundary returns
`SourcePermissionDecision(decision=DENY, rule=...)`.

#### Scenario: actor without network.local cannot egress to a public host

Given an actor carrying `network.external`
When the egress policy evaluates
`EgressRequest(url="https://example.com/api",
classification=PUBLIC, capability_requested=network.external)`
Then the request is ALLOW (per the documented policy
that grants non-localhost egress to actors that hold
`network.external`).

### Requirement: Operator approval for high-impact security operations (§68.50)

Per the §68.50 architectural invariant, high-impact
security operations MUST route through the Phase 7
`REQUIRE_APPROVAL` / `approval_token` contract. The
Enterprise Boundary enforces the rule at the egress
boundary; a missing or invalid `approval_token` on a
high-impact operation is DENY (fail-closed).

The high-impact operation list (extendable through the
canonical configuration under `project-knowledge/
security/egress-high-impact.yaml`):

- RESTRICTED egress to an external endpoint
  (the destination's classification matches or exceeds
  the configured `RESTRICTED` ceiling);
- change of the endpoint allow-list (admin operation,
  enforced through the Phase 7 Policy Engine
  `RETRIEVAL_ADMIN` capability).

#### Scenario: RESTRICTED egress without approval_token is DENY

Given an
`EgressRequest(url="https://example.com/api",
classification=RESTRICTED,
capability_requested=network.external)` and the actor
holds `network.external` but no `approval_token`
When the egress policy evaluates the request
Then the egress decision is
`EgressDecision(allowed=False,
rationale="policy decision 'REQUIRE_APPROVAL' for
'network.external'; RESTRICTED egress requires an
approval_token",
channel=external)`.

#### Scenario: RESTRICTED egress with approval_token is ALLOW

Given an
`EgressRequest(url="https://example.com/api",
classification=RESTRICTED,
capability_requested=network.external,
approval_token="approved-by-cto")` and the actor holds
`network.external`
When the egress policy evaluates the request
Then the egress decision is
`EgressDecision(allowed=True,
rationale="capability=network.external and
endpoint_allow contains RESTRICTED",
channel=external)`
And an `AuditRecord(operation=security.egress,
result=ALLOW, resource=https://example.com/api)` is
emitted through the wired `AuditLogPort`.

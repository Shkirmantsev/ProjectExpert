# audit-log Specification delta

## Purpose

Expose the strict two-stream Audit Log / Operational Log separation and the no-secret-in-audit invariant.

## Requirements


### Requirement: Audit Log records the documented §59.13 fields

The Audit Log MUST record the documented §59.13 fields:

```text
timestamp
correlationId
projectVersion
actorType
actorId
plugin/agentId
operation
resource
policyDecision
result
duration
```

Every field MUST be present in every audit record; missing
fields MUST raise the typed `InvalidAuditRecordError`. The
Audit Log MUST be append-only; updates and deletes MUST NOT
be supported.

#### Scenario: audit record contains every documented field

Given an MCP tool consults the policy engine
When the audit log records the decision
Then the audit record carries every documented §59.13
field
And the record is appended to the audit stream.

### Requirement: Audit Log MUST NOT contain a raw secret value

The Audit Log MUST NOT contain a raw secret value. The
audit writer MUST apply the Phase 7 `SecretProvider` redaction
filter to every value before it is written to the audit
stream. The filter MUST replace every resolved secret value
with the documented redacted form
(`secret://<backend>/<name>[REDACTED]`). An audit writer
that attempts to write a raw secret value MUST raise the
typed `SecretLeakageError` and MUST abort the write.

#### Scenario: audit writer aborts on a raw secret value

Given the policy engine decision carries the resolved
value `"http://proxy:8080"` for the reference
`env://HTTP_PROXY`
When the audit writer attempts to write the record
Then the audit writer applies the redaction filter
And the audit stream contains
`"env://HTTP_PROXY[REDACTED]"` instead of the raw value.

### Requirement: Audit Log and Operational Log MUST NOT share a sink or a writer

The Audit Log and the Operational Log MUST NOT share a sink
or a writer. The two streams MUST be backed by separate
writers, separate sinks and separate file descriptors (where
applicable). The control plane MUST refuse to start if the
configured audit sink path matches the configured operational
sink path. The control plane MUST refuse to start if the two
streams share a writer instance.

#### Scenario: control plane refuses to start on sink collision

Given the configured audit sink path is
`/var/log/pi/audit.jsonl`
and the configured operational sink path is
`/var/log/pi/audit.jsonl`
When the control plane starts
Then the control plane raises
`AuditOperationalSinkCollision`
And the control plane exits with a non-zero code.

### Requirement: Operational Log records diagnostics, errors, performance and health

The Operational Log MUST record diagnostics, errors,
performance and health. The Operational Log MUST NOT
contain audit records; the Operational Log MUST NOT be
consulted for security / state-relevant queries. The
Operational Log and the Audit Log MUST remain strictly
separated.

#### Scenario: operational log records an error

Given a parser fails to ingest a document
When the ingestion pipeline records the failure
Then the failure is written to the Operational Log
And the failure is NOT written to the Audit Log.

### Requirement: Audit Log supports time-range and correlation-id queries

The Audit Log MUST support time-range queries and
correlation-id queries. The query result MUST be a JSONL
stream of audit records; the query result MUST NOT include
resolved secret values. The query API MUST NOT expose a
delete operation; only append and read are supported.

#### Scenario: audit query returns matching records

Given three audit records share the correlation id
`corr-123`
When the operator queries the audit log by correlation id
Then the audit log returns the three matching records
And the records carry every documented §59.13 field
And no record contains a raw secret value.

### Requirement: Audit Log serialise and flush are byte-stable

The audit log serialise and flush MUST be byte-stable. Two
consecutive `serialise()` calls on the same audit log
MUST return byte-identical JSON. Two consecutive `flush()`
calls MUST produce byte-identical JSONL output. The
serialised / flushed form MUST NOT include resolved secret
values.

#### Scenario: flush is byte-stable

Given the audit log has recorded five audit records
When the operator invokes `flush()` twice
Then the two returned JSONL streams are byte-identical.
And neither stream contains a raw secret value.

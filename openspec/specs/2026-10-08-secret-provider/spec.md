# secret-provider Specification delta

## Purpose

Expose the Secret Provider with the secret:// / env:// reference vocabulary and mandatory redaction in MCP / A2A / audit / LLM context channels.

## Requirements


### Requirement: Secret Provider supports the documented reference vocabulary

The Secret Provider MUST accept the documented reference
vocabulary:

```text
secret://local/<name>
secret://enterprise/<name>
env://<name>
```

The provider MUST reject any reference outside the
documented vocabulary with the typed
`InvalidSecretReferenceError`. The provider MUST parse
references into a typed `SecretReference` carrying
`scheme`, `backend`, `name` and `version`. The provider
MUST NOT log or persist raw secret values; only the
`SecretReference` is allowed in registry / audit /
materialised state.

#### Scenario: provider rejects an unknown scheme

Given a reference `vault://local/insecure`
When the provider parses the reference
Then the provider raises `InvalidSecretReferenceError`
with `scheme="vault"`.

#### Scenario: provider parses a valid reference

Given a reference `secret://local/confluence-token`
When the provider parses the reference
Then the provider returns
`SecretReference(scheme="secret", backend="local", name="confluence-token")`.

### Requirement: Secret Provider resolves references through the documented backends

The Secret Provider MUST resolve references through the
documented backends: OS keychain, environment variables,
encrypted local store and (optionally) enterprise vault.
The provider MUST raise the typed `SecretResolutionError`
when the backend is unavailable, the reference is unknown
or the calling actor is not authorised for `secret.resolve`.
The provider MUST cache resolved values in memory only;
the cache MUST honour the documented TTL and MUST be
invalidatable through `invalidate(reference)`.

#### Scenario: provider raises SecretResolutionError for an unknown reference

Given a reference `secret://local/missing`
When the provider attempts to resolve the reference
Then the provider raises `SecretResolutionError`
And the calling consumer MUST translate the error into
`DENY` if the calling capability is `secret.resolve`.

#### Scenario: provider resolves an env:// reference

Given a reference `env://HTTP_PROXY`
and the environment variable `HTTP_PROXY=http://proxy:8080`
When the provider resolves the reference
Then the provider returns the string `"http://proxy:8080"`.

### Requirement: Secret Provider redacts resolved values in MCP responses, A2A payloads, audit payloads and LLM context

The Secret Provider MUST expose a `redact(value, context)`
filter that replaces every resolved secret value with the
documented redacted form
(`secret://<backend>/<name>[REDACTED]`) when the value
appears in:

- MCP responses;
- A2A payloads (unless explicitly authorised through the
  policy engine capability `network.external` or
  `secret.resolve`);
- audit payloads;
- LLM context (the assembled task context bundle).

The redaction filter MUST be applied by every consumer that
serialises a value to one of the four channels. The
redaction filter MUST NOT mutate the resolved value itself;
the filter returns a copy.

#### Scenario: MCP response redacts a resolved secret

Given a MCP response carries the resolved value
`"http://proxy:8080"` for the reference
`env://HTTP_PROXY`
When the MCP server applies the redaction filter
Then the response carries
`"env://HTTP_PROXY[REDACTED]"` instead of the raw value.

#### Scenario: LLM context redacts a resolved secret

Given a `ContextBundle` carries the resolved value
`"http://proxy:8080"` for the reference `env://HTTP_PROXY`
When the context assembler applies the redaction filter
Then the bundle carries `"env://HTTP_PROXY[REDACTED]"`
instead of the raw value.

### Requirement: The runtime database MUST NOT contain a plain-text secret value

The runtime database MUST NOT contain a plain-text secret
value. The database MAY contain `SecretReference` records;
it MUST NOT contain the resolved value. The provider MUST
reject any attempt to persist a resolved value through the
Phase 1 `MaterialiseService`. The Phase 1 `LicenseGate` MUST
extend its check to forbid runtime databases that contain
plain-text secret values; the gate MUST emit the typed
`LicenseGateFinding(severity="forbid", rule="no_plain_text_secret")`.

#### Scenario: materialise rejects a secret value in the payload

Given the materialise payload carries the resolved value
`"http://proxy:8080"`
When the materialise service serialises the payload
Then the materialise service raises `InvalidMaterialisePayload`
And the materialise service records an audit entry with
`operation=materialise.secret_violation`,
`result=denied`.

### Requirement: Secret Provider serialise is byte-stable

Two consecutive `serialise()` calls on the same provider
MUST return byte-identical JSON. The serialised form MUST
include the registered `SecretReference` records, the
configured backends and the cache TTL. The serialised form
MUST NOT include resolved secret values.

#### Scenario: serialise is byte-stable

Given the provider has registered three references and
two backends
When the operator invokes `serialise()` twice
Then the two returned JSON strings are byte-identical.
And neither string contains a resolved secret value.

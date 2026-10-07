# Versioning Reference

This document specifies the §39 nine-dimension compatibility
handshake the MCP server and the canonical Agent Skill
implement.

## The nine dimensions

The platform tracks:

- `platformVersion` — the platform package release.
- `mcpApiVersion` — the product tool-schema API exposed by
  the MCP server. Independent of the MCP SDK package version
  and the MCP wire protocol version.
- `a2aAdapterVersion` — UNIMPLEMENTED until Phase 10.
- `knowledgeSchemaVersion` — the canonical knowledge schema.
- `okfProfileVersion` — supported OKF profile versions.
- `skillVersion` — the canonical Agent Skill version.
- `pluginDistributionSchemaVersion` — release manifest
  schema identifier (not semver).
- `agentAdapterVersion` — UNIMPLEMENTED until Phase 7+.
- `runtimeIndexSchemaVersion` — the runtime index schema
  version (UNIMPLEMENTED until Phase 7+).

## Semver ranges

Semver MAJOR.MINOR.PATCH ranges apply to:

- `platformVersion` — e.g. `>=0.8.0 <1.0.0`.
- `mcpApiVersion` — e.g. `>=1.3.0 <2.0.0`.
- `knowledgeSchemaVersion` — e.g. `>=0.7.0 <1.0.0`.
- `skillVersion` — e.g. `>=1.4.0 <2.0.0`.

## Identifier sets

`okfProfileVersion` is an identifier set, not a semver range.
The server currently advertises `{"0.2"}`. Clients pick one
member of the set. `pluginDistributionSchemaVersion` is an
identifier set (`{"1"}`) and clients pick one member of the
set.

## Unavailable dimensions

`a2aAdapterVersion`, `agentAdapterVersion` and
`runtimeIndexSchemaVersion` are reported as `available: false`
in the `dimensions` block of `describe_capabilities` until
their respective phases ship. Clients MUST NOT compare
unavailable dimensions against invented values; the verifier
skips them.

## Typed `VersionIncompatibleError`

When the handshake fails, the server returns a typed error:

```json
{
  "type": "VersionIncompatibleError",
  "dimension": "mcpApiVersion",
  "serverOfferedRange": ">=1.3.0 <2.0.0",
  "clientOfferedValue": "2.0.0",
  "applicableAdapter": "codex",
  "upgradeInstructions": "the client advertises an unsupported ..."
}
```

`serverOfferedRange` is the range the server advertised for
the failing dimension; `clientOfferedValue` is the value the
client declared. `applicableAdapter` is the name of the adapter
the client configured, when known; it is `null` otherwise.

## Skill / server negotiation

At connection / startup:

1. the client reads `project.describe_capabilities`;
2. the client compares its own version block against the
   server's compatibility range;
3. if compatible, continue;
4. otherwise fail with the typed payload above.

The server exposes capability information without requiring
an LLM round-trip. The handshake is deterministic and
byte-stable.
---
id: interfaces.dependency-research
title: Dependency research interfaces
kind: interfaces
status: active
summary: The MCP and A2A shapes of the dependency research: tools, the versioned A2A envelope, typed errors, capability discovery and provenance.
---

# Dependency research interfaces

The dependency research is reachable over two transports. Both call
the same service (`modules.dependency-research`), so the answers
match; only the wire wrapper differs.

## MCP tools

| Tool | Arguments | Result |
|---|---|---|
| `project.dependency_tree` | `ecosystem` (required), `package`, `environment`, `scopes`, `max_depth`, `max_nodes`, `cursor` | the evidence-backed graph, the why-paths, the effective limits, the scope and the truncation state |
| `project.dependency_search` | `ecosystem`, `package_ref`, `query` (required), `limit`, `cursor` | symbol cards with their evidence reference and representation |
| `project.dependency_read` | `evidence_ref`, `artifact`, `member`, `symbol`, `start_line`, `end_line`, `max_bytes` | a bounded excerpt with its line range, digest and representation |
| `project.dependency_acquire` | `ecosystem`, `name`, `version`, `source_id` (required) | the cached artifact, its digest and its members |

`project.get_dependency` keeps its historical Maven argument shape
(`group`, `artifact`, `version`) and now answers from the real
dependency graph: the declared and resolved versions of the
coordinate, the matching instances and the evidence behind them. A
coordinate the graph does not contain is reported as `unavailable`
with the reason. The tool never answers with a placeholder.

Every research tool returns `{ok, research, status, completeness,
warnings, truncated, cursor}`. A failure is a typed status
(`denied`, `unsupported`, `stale`, `failed`), not an empty success.

## A2A envelope

A research request is a **data** part with a versioned envelope:

```json
{"schema_version": 1, "operation": "dependency.tree",
 "arguments": {"ecosystem": "python", "max_depth": 3}}
```

The allowlisted operations are `dependency.tree`,
`dependency.search`, `dependency.read` and `dependency.acquire`.
An unknown operation, an unknown envelope version and a surface
without a wired research service are **rejected**; they never
succeed as a generic acknowledgement. The answer is one
`application/json` artifact named `research` that carries the same
result schema as the MCP answer.

The legacy non-research behaviour is unchanged: a task without an
envelope still returns the deterministic `ack` artifact. The
inbound flag (`PI_A2A_INBOUND`), the policy gate, the actor
capability check, the secret redaction and the per-actor limits
still apply to a research request.

## Capability discovery

`project.describe_capabilities` reports the research capability
from the wiring: the ecosystems that are present, whether
acquisition is enabled, the approved sources and the availability
of the optional Node parser. A capability that is not wired is not
advertised, and the agent card only offers the research skill when
the service is wired.

## Provenance

Every answer carries evidence references. A Wiki enrichment records
the same references in `dependency_notes` together with the package,
the version, the artifact hash, the repository revision and the
tool version, and a label that separates an observed fact from an
inference. See [`modules.llm-wiki`](../modules/llm-wiki.md).

## Related

- [`modules.dependency-research`](../modules/dependency-research.md)
- [`interfaces.mcp-tools`](mcp-tools.md)
- [`interfaces.a2a`](a2a.md)
- `docs/DEPENDENCY_RESEARCH.md`

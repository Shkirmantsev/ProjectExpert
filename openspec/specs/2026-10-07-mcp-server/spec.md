# mcp-server Specification delta

## Purpose

Expose platform retrieval, knowledge, orchestration, and approval-controlled write capabilities through semantic MCP tools and capability discovery.

## Requirements

Covers architecture section §36 (MCP Integration) and §47
(Capability Discovery). The MCP server exposes the platform's
Phase 1-5 surface as 17 semantic tools plus the
`describe_capabilities` descriptor tool. The MCP server is a
thin adapter; it composes the Phase 5 `QueryOrchestratorPort`,
`LocalLLMPort`, `TaskContextBuilderPort` and
`CapabilityDiscoveryPort`, and the Phase 4
`MultiStageRetrievalPort` / `HybridRetrievalPort` /
`ContextAssemblerPort`, without introducing a new runtime
store.

The 17 semantic tools are the canonical MCP tool surface
documented in §36:

```text
project.search
project.retrieve_context
project.get_entity
project.get_component
project.get_requirement
project.get_spec
project.get_architecture
project.get_dependency
project.find_implementation
project.trace_requirement
project.find_references
project.get_project_version
project.get_conflicts
project.get_stale_knowledge
project.build_task_context
project.materialize_knowledge
project.refresh_sources
```

`describe_capabilities` returns the §47
`CapabilityDescriptor` that the Phase 5
`CapabilityDiscoveryPort` produces. The public tools hide storage primitives. Retrieval and context tools use
Phase 4 / Phase 5 retrieval-first policy. Exact entity, graph, version,
provenance and sync operations delegate to their owning ports/services;
they do not invoke retrieval or an LLM solely to perform an exact lookup.

### Requirement: MCP server composes the Phase 5 / Phase 4 surface

The platform MUST expose an `McpServer` thin adapter in
`pi_platform/mcp/server.py` that composes the existing
`QueryOrchestratorPort`, `LocalLLMPort`,
`TaskContextBuilderPort` and `CapabilityDiscoveryPort`
(Phase 5), the `MultiStageRetrievalPort`,
`HybridRetrievalPort` and `ContextAssemblerPort` (Phase 4)
and the Phase 1 `MaterialiseService` through the 17 semantic
tools plus `describe_capabilities`. The MCP server MUST
NOT introduce a new runtime store; it MUST NOT bypass the
Phase 4 / Phase 5 retrieval and orchestration invariants
and MUST NOT modify the Phase 1-5 capability specs.

#### Scenario: MCP server delegates retrieval to Phase 4 / Phase 5

Given an MCP client calls `project.search`
When the MCP server processes the call
Then the MCP server delegates to the Phase 5
`QueryOrchestratorPort.orchestrate` (or the Phase 4
`MultiStageRetrievalPort.retrieve` for tool-level bypass)
And the retrieval-first violation counter (`stats()
["retrieval_first_violations"]`) is unchanged.

#### Scenario: MCP server does not introduce a new runtime store

Given the MCP server is started
When the operator inspects the registered ports
Then no new runtime store is registered beyond the Phase 3
`RuntimeStore`, the Phase 3 sparse / dense / full-text
indexes, the Phase 3 sharded graph and the Phase 4 / Phase
5 adapters.

### Requirement: 17 semantic tools with stable schemas

The MCP server MUST expose the 17 §36 semantic tools. Every
tool MUST declare a typed input schema, a typed output
schema and a deterministic side-effect profile. The 17
tools MUST NOT be renamed, removed or replaced without a
documented backwards-compatible alias; the 17-tool list is
the documented exhaustive surface per §36. Additional tools
may be added only as documented extensions and MUST NOT
shadow the §36 names.

The 17 tools and their primary inputs / outputs are:

| Tool | Primary input | Primary output |
|---|---|---|
| `project.search` | `query: str`, optional `level: int`, optional `filters: dict` | `OrchestrationResult` (Phase 5) |
| `project.retrieve_context` | `query: str`, `budget_tokens: int`, optional `filters: dict` | `ContextBundle` (Phase 4 `ContextAssemblerPort`) |
| `project.get_entity` | `entity_id: str` | entity record (Phase 3 graph) |
| `project.get_component` | `component_id: str` | component record |
| `project.get_requirement` | `requirement_id: str` | requirement record |
| `project.get_spec` | `spec_id: str` | OpenSpec spec record |
| `project.get_architecture` | `section: str` | architecture reference |
| `project.get_dependency` | `target_id: str` | dependency edges |
| `project.find_implementation` | `symbol: str`, optional `kind: str` | implementation hits |
| `project.trace_requirement` | `requirement_id: str` | requirement trace edges |
| `project.find_references` | `symbol: str`, optional `scope: str` | reference hits |
| `project.get_project_version` | (no input) | current Git version |
| `project.get_conflicts` | (no input) | conflict report |
| `project.get_stale_knowledge` | (no input) | stale-knowledge report |
| `project.build_task_context` | `goal: str`, optional `requirement_id: str`, optional `budget_tokens: int`, optional `filters: dict` | `TaskContextBundle` (Phase 5) |
| `project.materialize_knowledge` | `entries: list`, `approval_id: str` | materialisation report |
| `project.refresh_sources` | `sources: list[str]` (optional), `approval_id: str` | refresh report |

#### Scenario: every §36 tool is registered

Given the MCP server is started with the default
registrations
When the operator enumerates the registered tools
Then the set of tool names is exactly the 17 §36 tools plus
`describe_capabilities`.

#### Scenario: tool schemas are stable across restarts

Given a fixed platform state
When the MCP server enumerates its tools
Then the input / output JSON schemas for the 17 tools plus
`describe_capabilities` are byte-identical across
restarts.

### Requirement: describe_capabilities returns the §47 descriptor

The MCP server MUST expose `describe_capabilities` that
returns the `CapabilityDescriptor` from the Phase 5
`CapabilityDiscoveryPort.describe`. The MCP server MUST NOT
regenerate the descriptor; it MUST delegate to the port so
the descriptor stays the single source of truth.

#### Scenario: describe_capabilities matches the port

Given the Phase 5 `CapabilityDiscoveryPort` is registered
When a client calls `describe_capabilities`
Then the returned JSON is identical (modulo byte-order)
to the JSON returned by
`CapabilityDiscoveryPort.describe()`.

### Requirement: capability discovery does not require an LLM

The MCP server MUST expose capability information without
requiring an LLM. The `describe_capabilities` tool MUST NOT
call the local LLM or any external LLM; the descriptor is
computed deterministically from the registered port
registry.

#### Scenario: describe_capabilities works without a local LLM

Given the stub `LocalLLMPort` is registered (`is_available
() == False`)
When a client calls `describe_capabilities`
Then the call returns successfully
And the descriptor reports `features.localLlm == False`.

### Requirement: write / materialisation tools require approval

The MCP server MUST require an explicit `approval_id` (or
the platform's documented approval artefact) for every call
to a write / materialisation tool
(`project.materialize_knowledge`,
`project.refresh_sources`). The MCP server MUST refuse calls
without a valid approval and MUST NOT route them to the
Phase 1 `MaterialiseService`. The MCP boundary MUST enforce DENY and validate approval authenticity and
scope before mapping the approved request to `MaterialiseService` or the
ingestion driver. A caller-chosen nonempty token is not proof of approval.
`refresh_sources` delegates to ingestion, not to materialisation. The existing
Phase 1 policy stub does not issue or validate approval identifiers; the
prerequisite fix is documented in the design.

#### Scenario: materialisation requires an approval_id

Given an MCP client calls
`project.materialize_knowledge` without an `approval_id`
When the MCP server processes the call
Then the MCP server raises a documented
`ApprovalRequiredError`
And the call is NOT routed to the `MaterialiseService`.

#### Scenario: materialisation succeeds with a valid approval_id

Given an MCP client calls
`project.materialize_knowledge` with a valid `approval_id`
validated by the trusted approval boundary for the requested operation
When the MCP server processes the call
Then the call is delegated to the Phase 1
`MaterialiseService`
And the materialisation report is returned.

### Requirement: retrieval-first semantic routing

The MCP server MUST prefer exact lookup for known identifiers and bounded
retrieval for semantic questions. Tool enumeration order MUST NOT be treated
as enforcement of retrieval-first behavior. Filtered requests MUST preserve
project, Git version and security eligibility through every lookup, graph
traversal, context assembly and orchestration step; an unsupported filter or
level combination MUST fail explicitly rather than drop filters.

#### Scenario: filtered semantic query preserves eligibility

Given a query restricted to a project version and security scope
When `project.search` or `project.retrieve_context` is called
Then all returned evidence satisfies that scope
And an unsupported filtered L1/L2 request fails with a documented error.

#### Scenario: exact lookup respects security and version scope

Given an entity outside the session's authorized project or Git version
When a client performs exact lookup or traces its relations
Then no ineligible record or edge is returned.

### Requirement: hydrate before serving project knowledge

The MCP server MUST wait for a consistent hydrate/reconcile report before
serving project knowledge, following the accepted bidirectional sync contract.
A branch change MUST reconcile before returning results for the new version.

#### Scenario: inconsistent hydration prevents serving

Given hydrate reports an inconsistent state
When the MCP server starts or a branch switch is detected
Then project-knowledge calls fail with a documented readiness error
And inconsistent or cross-version evidence is not returned.

### Requirement: provenance and citation metadata are returned

The MCP server MUST return provenance (`source`,
`version`, `commit`, `license`, `confidence`) and citation
fields on every tool result that returns knowledge. Tools
that return ephemeral state (e.g. the materialisation
report) MAY omit citation metadata.

#### Scenario: project.get_entity returns provenance

Given an MCP client calls `project.get_entity` with a
known `entity_id`
When the MCP server processes the call
Then the result carries `provenance.source`,
`provenance.version`, `provenance.commit`,
`provenance.license` and `citation` fields
And the values match the Phase 3
`ProvenancePort.evidence(entity_id)` records and canonical source metadata.
Unavailable provenance fields are explicitly marked unavailable and MUST NOT
be fabricated.

### Requirement: MCP server reports version compatibility errors

The MCP server MUST report a typed
`VersionIncompatibleError` when an MCP client's handshake
declares an MCP API version the server cannot satisfy. The
error MUST include the server's `mcpApiVersion`, the
client's declared `mcpApiVersion` and the supported range.

#### Scenario: handshake reports a typed error

Given an MCP client declares an MCP API version that does
not intersect the server's supported range
When the client opens a session
Then the MCP server returns a
`VersionIncompatibleError`
And the error message reports the server `mcpApiVersion`,
the client declared range and the supported range.

### Requirement: MCP server transport and SDK

The MCP server MUST use the official MCP Python SDK (the
`mcp` package; SPDX `Apache-2.0`) to expose the FastMCP
typed tool surface. The MCP server MUST support both
stdio and HTTP transports; the default transport is stdio.
The MCP server MUST ship in the default container.

#### Scenario: default transport is stdio

Given the MCP server is started without explicit transport
configuration
When the server boots
Then it listens on the stdio transport.

### Requirement: MCP retrieval tools fail closed during refresh

The MCP retrieval tools (`kb_search`, `kb_query`,
`task_context_build` and any future retrieval tool) MUST return
a structured `refreshing` or `not_ready` result while a
reconciliation is in progress. The tools MUST NOT serve the
previous branch evidence as if it were the current branch.

#### Scenario: kb_search returns refreshing during reconciliation

Given a reconciliation for the active project is in progress
When the MCP client calls `kb_search`
Then the response carries a structured `refreshing` result
And the previous branch evidence is not returned
And the response identifies the active refresh job identifier.

### Requirement: MCP retrieval uses the unified production composition

The MCP retrieval tools MUST be backed by the same
`build_production_retrieval_runtime` composition used by the
web UI. Two tool implementations with materially different
search semantics for the same query MUST NOT coexist.

#### Scenario: MCP and UI return identical results

Given the same query and the same runtime configuration
When the query is executed through `kb_search` and through the
web UI
Then both responses contain the same ranked candidates
And both responses carry equivalent retrieval metadata.

### Requirement: model switch is administrator-only

The MCP server MUST refuse a model switch request from a
client that does not carry the documented administrator
capability. The refusal MUST be a structured authorisation
error, not an opaque failure.

#### Scenario: ordinary agent cannot switch models

Given a client capability that is not the administrator
capability
When the client calls the model switch tool
Then the tool returns a structured authorisation error
And the active embedding profile is unchanged.

### Requirement: Interoperable transport
The server SHALL provide standard initialize serverInfo.version and complete argument schemas, accept notifications without JSON-RPC replies, and return 405 for unsupported GET streams.

#### Scenario: Clean external repository
- **WHEN** the user starts the platform in a clean external repository
- **THEN** the runtime follows this contract without development-harness prerequisites

### Requirement: the caller may control reranking per query

The MCP retrieval tools MUST let the caller override the operator
reranking policy for a single query. The override MUST NOT change the
configured policy for any other query.

#### Scenario: the caller enables reranking for one query

Given a deployment whose policy disables reranking
When the caller asks the MCP retrieval tool for reranking
Then the query is executed with reranking enabled
And the configured policy is unchanged

#### Scenario: the caller disables reranking for one query

Given a deployment whose policy enables reranking
When the caller asks the MCP retrieval tool not to rerank
Then the query is executed without reranking
And the configured policy is unchanged

### Requirement: the MCP server exposes the LLM Wiki surface

The MCP server MUST expose the LLM Wiki tools alongside the canonical
tool names. The tool names MUST NOT shadow the canonical §36 names.

The Wiki tools MUST NOT require the operator approval id. The existing
rule that the write and materialisation tools require it MUST continue to
apply to the derived-knowledge tools.

#### Scenario: the Wiki tools are listed

Given an MCP server
When the client lists the tools
Then the LLM Wiki tools are listed
And the canonical tool names are unchanged

#### Scenario: the Wiki tools do not require an approval id

Given a target repository with an initialised Wiki
When the caller writes a curated page
Then the write succeeds without an approval id
And the derived materialisation tools still refuse a call without an
approval id

### Requirement: Dependency research tool surface
MCP SHALL expose schema-described graph, symbol-search, code-read and explicit artifact-acquisition operations backed by shared research logic. Arguments and outputs SHALL enforce project boundaries, budgets and policy. Existing get_dependency Maven arguments SHALL remain valid and return evidence or an explicit unavailable/partial result, never echoed coordinates as proof.

#### Scenario: Tools discovery and execution
- **GIVEN** a bound repository with a known transitive dependency fixture
- **WHEN** a client initializes, lists tools and requests its graph then code
- **THEN** schemas validate and returned records reference actual fixture evidence

#### Scenario: Legacy Maven lookup
- **GIVEN** an existing client using group, artifact and version
- **WHEN** get_dependency is invoked
- **THEN** input compatibility is preserved and the result is evidence-backed or explicitly unavailable

#### Scenario: Isolation and errors
- **GIVEN** a request for another repository or invalid evidence reference
- **WHEN** a research tool is invoked
- **THEN** access fails with a bounded structured error and no source leakage

## Phase 6 task coverage

The change covers Phase 6 task 85 (MCP server exposing
17 semantic tools + `describe_capabilities`). Task 86
(skill distribution resources), task 88 (version
handshake) and task 94 (plugin supply-chain security
gate) provide the supporting contracts. Task 87
(canonical Agent Skill) defines the skills / plugins the
MCP server distributes.

Out of scope:

- the skill distribution resources — Phase 6 task 86
  (`skill-distribution-plane`);
- the canonical Agent Skill content — Phase 6 task 87
  (`agent-skill-canonical`);
- the version-compatibility handshake — Phase 6 task 88
  (`version-compatibility-handshake`);
- the Codex / ChatGPT plugin package — Phase 6 task 89
  (`codex-plugin-package`);
- the Claude Code plugin package — Phase 6 task 90
  (`claude-code-plugin-package`);
- the OpenCode plugin package — Phase 6 task 91
  (`opencode-plugin-package`);
- the generic agent bundle — Phase 6 task 92
  (`generic-agent-bundle`);
- the agent adapter contract — Phase 6 task 93
  (`agent-adapter-contract`);
- the plugin supply-chain security gate — Phase 6 task 94
  (`plugin-supply-chain-security`);
- the Wiki maintenance and archive — Phase 6 task 95
  (`phase-6-wiki-archive`);
- A2A integration — Phase 10 tasks 119-123;
- the Control Plane and Feature / Plugin Registry —
  Phase 7 tasks 96-100;
- the enterprise security boundary — Phase 8 tasks
  105-110;
- the distribution one-click launcher — Phase 9 tasks
  111-118.

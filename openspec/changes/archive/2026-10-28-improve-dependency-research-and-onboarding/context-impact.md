# Context impact

All updates below are implementation tasks. Planning must not present them as shipped knowledge.

## Knowledge to create

| Proposed node | Purpose | When |
|---|---|---|
| `.ai/wiki/modules/dependency-research.md` (`module.dependency-research`) | Shared service, graph ownership, adapters, limits, cache and failures | After service verification |
| `.ai/wiki/interfaces/dependency-research.md` (`interface.dependency-research`) | MCP/A2A shapes, errors, auth, provenance and examples | After transport parity checks |
| `docs/DEPENDENCY_RESEARCH.md` | User workflow and language/format support matrix | After verified vertical slices |
| `docs/USER_GUIDE.md`, `docs/ARCHITECTURE.md` | Interface/use-case guide and architecture/process explanation | README slice |

Check proposed stable IDs for collision before creating nodes. Runtime research pages instead belong to each target's `project-knowledge/wiki/`, under existing OKF concept rules.

## Knowledge to update

- `.ai/wiki/modules/ingest.md`, `.ai/wiki/interfaces/source-adapters.md`: language coverage, locks, artifact bounds and discovery exclusions.
- `.ai/wiki/interfaces/mcp-tools.md`, `.ai/wiki/modules/mcp-server.md`: actual tools, legacy lookup behavior, examples, structured errors and budgets.
- `.ai/wiki/interfaces/a2a.md`, `.ai/wiki/modules/a2a.md`: research dispatch versus generic acknowledgement, flags, authorization and limits.
- `.ai/wiki/modules/llm-wiki.md`: evidence metadata, stale knowledge, compare-and-write and storage/index distinction.
- `.ai/wiki/architecture/portable-deployment.md`: help default, consistent helper configuration and effective URL.
- `.ai/wiki/INDEX.md`, `docs/README.md`: navigation to new references after creation.
- `README.md`, `distribution/deployment/README.md`, `docs/PRODUCTION_INSTALL.md`, `docs/CONFIGURATION.md`, `docs/TROUBLESHOOTING.md`, `docs/PYTHON_DEPENDENCY_ANALYSIS.md`: keep commands, limits and support claims synchronized.
- Client agent instructions distributed by the project: Wiki-first research, bounded tool calls and evidence-based enrichment. Update canonical generator inputs before regenerating bundles.

## Knowledge to review for staleness

- README phase 9/10 claims contradict accepted/current source: remove historical phase status from user entry point and link maintained current-state evidence.
- `.ai/wiki/architecture/platform-overview.md`, `.ai/wiki/project/implementation-roadmap.md`: inspect relevant portions for equivalent stale claims; do not rewrite unrelated history.
- Dependency Wiki pages whose artifact/lock hashes changed: mark evidence stale; preserve explanations and references.
- `openspec/changes/ship-portable-oci-deployment` and `production-semantic-search-and-branch-reconciliation`: reconcile overlapping deployment/transport work; no duplicate adoption or unchecked task closure.

## Affected implementation

Modules and interfaces are listed in [design](design.md). Primary seams: `BuildTreeMixin.resolve_tree`, `JarAdapter`, Python intelligence adapters, `RepositorySourceDiscovery`, `_tool_get_dependency`, tool schemas/context, `A2aAdapterCore.invoke`, embedded composition, and `LlmWiki.write_page`.

## ADR impact

Review ADR 0029 (portable runtime/kit) and ADR 0030 (curated Wiki); preserve their boundaries. Create a new ADR only when choosing a durable cross-language research/decompiler isolation policy. Record optional parser/decompiler selection, license, supported versions and fallback; do not predeclare a vendor decision during planning.

## Acceptance criteria

- [ ] Relevant Wiki pages explain only shipped behavior and link normative specs.
- [ ] Target Wiki enrichment is validated and searchable after refresh.
- [ ] Implementation Wiki links and stable IDs validate; local index is refreshed via the harness.
- [ ] Existing dated spec identities are preserved; new capabilities receive first-acceptance dates on adoption.
- [ ] `openspec/CURRENT.md` changes only when behavior is adopted, and contains each accepted capability exactly once.
- [ ] Observed mismatches are resolved or explicitly retained as limitations with evidence.

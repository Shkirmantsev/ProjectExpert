# Proposal

## Why

Users need a quiet, understandable startup and evidence about the libraries their project actually uses. Today the deployment kit starts services on bare `make`; a reduced Compose configuration can report active sidecars as orphans. Python ingestion exists, but resolved dependency research is incomplete. The Maven-shaped MCP lookup is a placeholder, and A2A currently acknowledges tasks without performing research. The README mixes user setup with historical implementation detail.

## Goal

Deliver four outcomes in ordered, independently verifiable slices:

1. Bare `make` explains commands; explicit startup preserves healthy services and reports the correct URL.
2. Java, Python and JavaScript/TypeScript projects expose dependency graphs and inspectable library code, with truthful completeness and source provenance.
3. LLMs request bounded research through MCP or A2A, then enrich an existing project Wiki page so later queries can reuse it.
4. A short README offers container setup/run, a Python virtual-environment fallback, use cases, interfaces, capabilities and configuration links.

This change is **proposed**. This delivery supplies instructions for implementation agents; it does not implement or certify these outcomes. See [handoff](handoff.md), [evidence](evidence.md), [design](design.md), [tasks](tasks.md) and [README blueprint](readme-blueprint.md).

## Affected capabilities

Existing identities retained by deltas:

- `2026-10-11-one-click-distribution`: deployment Make help and consistent Compose topology.
- `2026-10-26-python-dependency-intelligence`: lock/installed metadata and targeted dependency inspection, preserving static ingestion.
- `2026-10-04-jar-dependency-intelligence`: bounded source/decompilation evidence.
- `2026-10-07-mcp-server`: real dependency research tools and compatibility.
- `2026-10-12-a2a-adapter`: research dispatch, not acknowledgement-only success.
- `2026-10-25-llm-wiki-curated-knowledge`: evidence-aware enrichment, conflicts, freshness and index visibility.

New proposed capabilities (assign first-acceptance dates only on adoption):

- `dependency-research`: shared graph, artifact acquisition, bounded reads and provenance contract.
- `javascript-dependency-intelligence`: Node manifests, locks, workspaces and library APIs.
- `user-onboarding`: concise, executable user documentation.

## Compatibility / migration impact

Bare `make` changes intentionally from startup to help in the deployment kit. Keep `make platform-start` and start scripts; update published instructions and test the exported kit. Preserve existing configuration and image pins during upgrades. Do not add automatic orphan removal.

Preserve Maven `project.get_dependency(group, artifact, version)` input compatibility. Add language-neutral tools; never return placeholder data as successful analysis. Preserve existing Python ingestion and source-search behavior. Offline inspection remains the default; acquisition is an explicit policy-controlled operation. New parsers and optional decompilers must not become prerequisites for the core harness.

Existing `.ai/wiki/` explains this implementation repository. Runtime research writes to the bound target's `project-knowledge/wiki/`; these are distinct stores. No automatic source rewriting, dependency installation, build-script execution, commits, or publication is in scope.

## Related knowledge

- `.ai/wiki/modules/ingest.md`, `.ai/wiki/interfaces/source-adapters.md`
- `.ai/wiki/interfaces/mcp-tools.md`, `.ai/wiki/interfaces/a2a.md`
- `.ai/wiki/modules/llm-wiki.md`, `.ai/wiki/adr/0030-llm-wiki-as-curated-knowledge.md`
- `.ai/wiki/architecture/portable-deployment.md`

Coordinate with active `ship-portable-oci-deployment` and `production-semantic-search-and-branch-reconciliation`; do not claim their unverified hardware/publication tasks are completed by this change.

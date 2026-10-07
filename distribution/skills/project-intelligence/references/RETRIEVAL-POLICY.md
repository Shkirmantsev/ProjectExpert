# Retrieval Policy Reference

This document specifies the §33 retrieval-first agent access
strategy the MCP server enforces on every read-only tool.

## The seven-step escalation

For an agent request:

1. exact symbol / metadata lookup (`project.get_entity`,
   `project.get_component`, `project.get_requirement`,
   `project.get_spec`, `project.get_dependency`);
2. sparse / BM25 / symbol search (`project.search` with the
   identifier);
3. dense semantic search (`project.search` hybrid fusion);
4. hybrid fusion (`project.retrieve_context`);
5. graph + hierarchy expansion
   (`project.find_implementation`,
   `project.find_references`, `project.trace_requirement`);
6. reranking (optional cross-encoder / ColBERT-style late
   interaction; used on bounded candidate sets);
7. bounded context assembly (`project.build_task_context`).

The orchestrator escalates to:

- L1 — retrieval + small local LLM for "explain" questions;
- L2 — strong external agent for "implement REQ-…" tasks;
- only when each lower step returned insufficient evidence.

Filters / project-version MUST be passed through L0 (typed
`RetrievalQuery`). L1 / L2 escalation REJECTS filtered queries
explicitly with
`FilteredEscalationNotSupportedError` until a separately
specified extension preserves the filters through the LLM call
or the task-context bundle.

## Filter / scope preservation

The orchestrator accepts:

- `filters`: a typed `MetadataFilter` (languages,
  businessDomains, modules, requirementIds,
  securityClassifications, queryDate, projectVersion);
- `project_version`: a typed `ProjectVersion` (gitHead,
  workingTreeFingerprint, knowledgeSchemaVersion,
  embeddingModelVersion, indexSchemaVersion).

For L0, the orchestrator passes them verbatim to
`MultiStageRetrievalPort.retrieve` so the metadata filter
stage of the pipeline enforces them. For L1 / L2 the
orchestrator raises `FilteredEscalationNotSupportedError`
with the level, the filters and the project_version so the
caller can re-issue the query with a narrowed filter set.

## Retrieval-first compliance

The orchestrator increments
`retrieval_first_violations` whenever it emits a task-context
bundle without prior retrieval evidence. The MCP server
records the same counter and surfaces it in
`describe_capabilities` (`retrievalFirstViolations: int`) so
agents can audit their own compliance.

## Token / context budget

`contextBudget` (default 2000 tokens) is the per-query bound
the multi-stage pipeline enforces via the §29 per-stage
budget reports. `project.build_task_context` accepts
`budget_tokens` (default 4000). Both numbers are surfaced in
`budgetUsed` of the response so the caller can audit
overspend.
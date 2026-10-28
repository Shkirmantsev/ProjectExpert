# MCP Tools Reference

The Phase 6 Project Intelligence MCP server exposes the
following tools. Tool names match the §36 architecture list
exactly; additional tools MUST NOT shadow these names.

## Read-only tools

### `project.search`

Hybrid exact + dense search.

Arguments:

- `text` (string, required): the search text. Identifiers
  like `GEN_3.0.03`, `RpaVaryToteJpaMapper`,
  `OrderStatus` MUST be searched exactly via the BM25 /
  symbol path; the dense path augments recall.
- `top_k` (integer, optional, default 10): maximum hits.
- `filters` (Object, optional): typed `MetadataFilter` with
  `languages`, `businessDomains`, `modules`, `requirementIds`,
  `securityClassifications`, `queryDate`, `projectVersion`.
- `project_version` (Object, optional): typed `ProjectVersion`
  with `gitHead`, `workingTreeFingerprint`,
  `knowledgeSchemaVersion`, `embeddingModelVersion`,
  `indexSchemaVersion`.

Returns: `RetrievalResult` (hits + stageReports + budgetUsed).

### `project.retrieve_context`

Multi-stage retrieval composing the §29 pipeline. Same
arguments as `project.search` plus `contextBudget` (integer).

### `project.get_entity`

Graph lookup for one entity. Arguments: `entity_id`,
`project_version`, `filters`. Returns the entity record plus
its `Evidence` (the `ProvenancePort.evidence` payload) and
`current_state`. Missing evidence is reported as missing, not
invented.

### `project.get_component`

Same as `project.get_entity` but indexed by component URI.

### `project.get_requirement`

Same shape, looking up by `requirementId`.

### `project.get_spec`

Same shape, looking up by OpenSpec spec id.

### `project.get_architecture`

Returns the architecture Wiki index for the current project
version.

### `project.get_dependency`

Returns the dependency record for one coordinate (group,
artifact, version). The argument shape is unchanged; the answer
is now real evidence: the versions the project declares or
resolves for the coordinate, the matching instances and the
evidence behind them. A coordinate that the dependency graph does
not contain is reported as `unavailable` with the reason — the
tool never answers with a placeholder.

### `project.dependency_tree`

The evidence-backed dependency graph of the project.

Arguments:

- `ecosystem` (string, required): `python`, `java` or `node`.
- `package` (string, optional): start the traversal at this
  package instead of at the project root.
- `environment` (string, optional, default `"default"`).
- `scopes` (array of strings, optional).
- `max_depth` (integer, optional, default 5).
- `max_nodes` (integer, optional, default 100).
- `cursor` (string, optional): the continuation token of a
  truncated traversal.

Returns: `{ok, research, status, completeness, warnings,
truncated, cursor}` where `research` carries the nodes, the
edges, the evidence references, the effective limits and the
scope of the answer. A cursor is bound to the snapshot, the
query and the policy: a cursor from another snapshot is
rejected as `stale`.

### `project.dependency_search`

Search the symbols of one dependency.

Arguments:

- `ecosystem` (string, required).
- `package_ref` (string, required): the package to search in.
- `query` (string, required): the symbol name or fragment.
- `limit` (integer, optional, default 20).

Returns: `{ok, research, ...}` with the symbol cards in
`research.excerpts`. Every card states the representation it was
read from (`source`, `stub`, `mapped-source`, `disassembly`,
`decompiled`).

### `project.dependency_read`

Read a bounded excerpt of library code.

Arguments:

- `evidence_ref` (string): the evidence reference of the code.
- `artifact` / `member` (strings, optional): the acquired
  artifact and the member inside it.
- `symbol` (string, optional): narrow the excerpt to one symbol.
- `start_line` / `end_line` (integers, optional).
- `max_bytes` (integer, optional).

Returns: `{ok, research, ...}` with the excerpt, its line range
and the representation it really has. A disassembly is not
recovered source and is labelled as such.

### `project.dependency_acquire`

Download one exact dependency artifact.

Arguments:

- `ecosystem` (string, required).
- `name` (string, required): the exact package name.
- `version` (string, required): the exact version.
- `source_id` (string, required): the approved registry identity,
  e.g. `"pypi"`.

Returns: `{ok, research, ...}` with the cached artifact, its
digest and the members it holds. Acquisition is denied when the
source is not approved by the deployment policy.

### `project.find_implementation`

Graph traversal from a requirement / spec id to its
implementing components / classes / methods. Arguments:

### `project.find_references`

Inverse of `project.find_implementation`: from a code symbol
to the requirements / specs that reference it.

### `project.trace_requirement`

End-to-end trace: requirement → spec → component → test.

### `project.get_project_version`

Returns the `VersionIdentity` for the current hydrate cycle.

### `project.get_conflicts`

Returns the conflict map (per-entity list of conflicts with
their `Evidence` chains).

### `project.get_stale_knowledge`

Returns the `staleness_map` from the provenance port.

### `project.build_task_context`

Builds a bounded task-context bundle from a goal and the
current retrieval evidence. Arguments: `goal`, `budget_tokens`,
optional `requirement_id`, optional `project_version`.

### `project.describe_capabilities`

Returns the `CapabilityDescriptor` (legacy short form) plus
the `dimensions` block (the §47 nine-dimension honest version
block).

## Write / materialisation tools

These require an `approval_id` issued by the trusted operator
boundary. The trusted boundary is a typed `ApprovalGrant`
authenticated with the configured operator signing key.

### `project.materialize_knowledge`

Materialise durable changes back to the canonical tree.
Requires `approval_id`. The server calls
`MaterialiseService.materialise_durable_changes` after
verifying the approval against the
`TrustedApprovalBoundary`.

### `project.refresh_sources`

Trigger a hydrate / reconcile cycle against the configured
sources. Requires `approval_id`.

## LLM Wiki tools

These tools expose the curated LLM Wiki — the Git-versioned OKF
v0.2 bundle at `project-knowledge/wiki/` of the target
repository. A curated page is a Markdown file with OKF
frontmatter; `type` is mandatory. Only `project.wiki_write_page`
writes, and it does NOT require an `approval_id`: it stores
curated knowledge, not derived materialisation. The derived
knowledge write tools above still require an `approval_id`.
Wiki tool failures return `{ok: false, error}` with `error` a
plain message string.

### `project.wiki_list_pages`

List the curated Wiki pages of the target repository.
Arguments: none.

Returns: `{ok, root, count, pages}` — one entry per curated page
(`{path, title, type, summary}`); the reserved `index.md` and
`log.md` are excluded.

### `project.wiki_read_page`

Read one curated Wiki page.

Arguments:

- `path` (string, required): Wiki-relative page path, e.g.
  `"architecture/overview.md"`.
- `include_body` (boolean, optional, default `true`): include
  the Markdown `body` and the parsed `frontmatter`.
- `inputs` (object, optional): the current state of the
  dependencies the page explains, keyed by package name, e.g.
  `{"requests": {"version": "2.32.4"}}`. The answer then reports
  the recorded evidence that is stale.

Returns: `{ok, page}` — `{path, title, type, summary, revision}`
plus `body`, `frontmatter` and `dependencyNotes` when
`include_body` is true, plus `staleNotes` when `inputs` was
given. The `revision` is the precondition of a later write.

### `project.wiki_search`

Search the curated pages by text overlap. The body is searched
too, so a page is findable by the content it explains and not
only by its title.

Arguments:

- `query` (string, required): free-text query over the curated
  pages.
- `top_k` (integer, optional, default 8): maximum hits.

Returns: `{ok, count, pages}` — the same page shape as
`project.wiki_list_pages`.

### `project.wiki_write_page`

Create or update one curated Wiki page. The page is rendered
with OKF frontmatter and validated against the OKF v0.2 profile
BEFORE it is stored — an invalid page is never written. The
write is atomic, cannot escape the Wiki root, is recorded in the
reserved `log.md`, and refreshes the navigation section of the
reserved `index.md`. The reserved `index.md` / `log.md`
themselves cannot be written through this tool. No
`approval_id`.

Arguments:

- `path` (string, required): Wiki-relative page path.
- `title` (string, required): human-readable page title.
- `body` (string, required): the Markdown body of the page.
- `type` (string, optional, default `"Concept"`): OKF concept
  type — one of `Concept`, `Architecture`, `Module`,
  `Interface`, `Process`, `Decision`, `Requirement`,
  `Glossary`, `Domain`, `Invariant`.
- `summary` (string, optional, default `""`): frontmatter
  summary.
- `author` (string, optional, default `"calling-llm"`): stored
  as `pi_author`.
- `source` (string, optional, default `""`): stored as
  `pi_source`.
- `dry_run` (boolean, optional, default `false`): validate and
  report without storing.
- `expected_revision` (string, optional): the revision the
  caller read. A page that changed in the meantime produces a
  conflict (`{ok: false, conflict: true, currentRevision}`)
  instead of a silent overwrite.
- `dependency_notes` (array of objects, optional): the
  provenance of the research the page explains — `package`,
  `ecosystem`, `version`, `artifactHash`, `evidence`,
  `repositoryRevision`, `toolVersion` and the `label`
  (`fact` or `inference`).

Returns: `{ok, written, stored, created, path, bytes, revision,
index_refreshed, index_state, retrieval_index_state,
dependency_notes, note}`. `stored` is the state of the page, and
`index_state` / `retrieval_index_state` the state of the two
indexes: the navigation index of the Wiki and the retrieval index
of the project. With `dry_run` the shape is `{ok, written: false,
dry_run: true, path, bytes, revision}`. `note` states that the
page becomes part of the searchable corpus on the next project
refresh — a written page is searchable after the next refresh,
not instantly through the dense index.

### `project.wiki_validate`

Validate the curated Wiki bundle against the OKF v0.2 profile.
Arguments: none.

Returns: `{ok, root, profile: "okf-0.2", errors}` — `ok` is
false when the bundle carries validation errors.

## Return shape

Every tool returns a JSON object with `ok: bool`. On failure,
the object carries `error: {type: str, message: str, ...}`.
Typed errors:

- `VersionIncompatibleError` — see `VERSIONING.md`.
- `FilteredEscalationNotSupportedError` — see
  `RETRIEVAL-POLICY.md`.
- `RuntimeNotReadyError` — see `SECURITY.md`.
- `ApprovalRejected` — see `SECURITY.md`.

## Resources

Resources are exposed under the §38 distribution URI
namespace:

- `project-intelligence://distribution/manifest`
- `project-intelligence://skills/index`
- `project-intelligence://skills/project-intelligence/<version>/SKILL.md`
- `project-intelligence://skills/project-intelligence/<version>/references/...`
- `project-intelligence://skills/project-intelligence/<version>/assets/...`

Every skill resource is content-addressed; two consecutive
reads return byte-identical bytes for any pinned version.
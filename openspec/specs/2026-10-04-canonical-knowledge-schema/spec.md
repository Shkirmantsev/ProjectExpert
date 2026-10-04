# canonical-knowledge-schema Specification

## Purpose
Define the stable, Git-versioned, deterministic, content-addressable
canonical knowledge model — including source, document, section,
chunk, contextual chunk, entity, relation, evidence, knowledge state,
project version, shard and manifest schemas — that every other
capability (ingestion, retrieval, graph, control plane, distribution)
depends on.

## Requirements

### Requirement: deterministic canonical serialization

Every canonical artifact (chunk, entity, relation, evidence,
manifest, OKF Markdown concept page) MUST be serialisable to a
deterministic textual form (JSON or YAML) such that two equivalent
runtime states produce byte-identical canonical files.

Deterministic serialization MUST cover at minimum:

- sorted keys in every JSON/YAML output;
- stable ordering of arrays of identifiers (sorted ascending by
  identifier string unless the array is semantically ordered and
  documented as such, e.g. chronology);
- canonical line endings (`\n`);
- canonical trailing newline at end of file;
- no embedded volatile data (timestamps, build paths, hostnames)
  inside the canonical artifact; volatile metadata, if any, lives
  in the manifest envelope, not the artifact body.

#### Scenario: equivalent chunks serialize byte-identically

Given two runtime chunks that differ only by field insertion order
in memory
When both are normalized to canonical form
Then the two serialized files are byte-identical.

#### Scenario: array ordering is sorted by identifier

Given an entity with three outgoing relations to entities `c-3`, `c-1`,
`c-2`
When the entity is serialized to canonical form
Then the relations array is sorted by target identifier to
`[c-1, c-2, c-3]`.

### Requirement: canonical object content addressing

Every canonical immutable object (parsed structure snapshot,
normalized chunk body, deterministic extracted relation, OKF concept
page snapshot) MUST be addressed by its SHA-256 hex digest of its
deterministic canonical serialization.

The content address MUST be used as the primary key for the runtime
working knowledge store cache and MUST be reused across Git branches
when the content has not changed.

#### Scenario: identical content shares the cache entry

Given two Git branches where the same source file produces the same
normalized chunk body
When the platform hydrates the second branch
Then the platform reports a cache hit for that content address in the
hydration report
And no second normalise step is performed for that body.

### Requirement: sharded canonical storage

Canonical knowledge MUST be persisted across multiple smaller files
rather than a single monolithic artifact. The following families MUST
be sharded:

- `graph/nodes/` — one shard per logical entity family
  (`requirements/`, `java-classes/`, `components/`, `specs/`,
  `dependencies/`, ...);
- `graph/edges/` — one shard per relation family (`implements/`,
  `depends-on/`, `calls/`, `tested-by/`, `references/`, ...);
- `objects/<hash-prefix[0:2]>/<hash-rest>.json` — content-addressed
  immutable objects, partitioned by the first two hex characters of
  the SHA-256 digest;
- `chunks/<source-family>/` — chunk shards per source family;
- `manifests/` — one JSON manifest per family
  (`knowledge-schema.yaml`, `source-manifest.yaml`,
  `graph-manifest.yaml`, `chunk-manifest.yaml`,
  `object-manifest.yaml`).

#### Scenario: large knowledge corpus stays sharded

Given a target project with 50k entities, 200k relations and 1M chunks
When the platform materialises durable knowledge
Then the canonical tree has at least 256 `objects/` shards, separate
entity-family shards, and separate relation-family shards
And no single file in the canonical tree exceeds 32 MiB.

### Requirement: manifest describes each knowledge family

Every knowledge family (graph, chunks, sources, objects) MUST have a
manifest file that records `schemaVersion`, shard identifiers, shard
paths, content hashes, source hashes, entity counts and shard
dependencies.

The runtime hydrate MUST use manifests as the primary entry point for
loading canonical knowledge; manifests MUST NOT be loaded lazily
across the network without operator consent.

#### Scenario: manifest drives hydration

Given a target project with a populated canonical tree
When the platform hydrates the runtime working knowledge store
Then the platform reads each manifest, compares its content hashes
with the cache, and only loads shards whose content hashes are absent
or changed
And the hydration reports per-family shard counts and cache hit
rates.

### Requirement: chunk model and hierarchy

Every chunk MUST contain at minimum:

- `id` (stable string identifier);
- `rawText` (the verbatim substring from the source);
- `contextualText` (the chunk text with attached parent headings,
  package, class, method, requirement ID, OpenSpec ID or other
  deterministic context);
- `metadata` (key/value map per §23);
- `parentId` (optional, points to a parent chunk or section);
- `childIds` (optional, ordered list of child chunks);
- `entityIds` (optional, ordered list of related entity identifiers);
- `sourceReference` (stable identifier for the source document /
  file / URI);
- `contentHash` (SHA-256 of `rawText`);
- `provenance` (verification status, source hash, parsing version).

Every chunk MUST be addressable via its `id` and via its
`contentHash`. The hierarchy MUST support at least three levels:
`Document > Section > Chunk`. Searchable representations MAY exist for
`documentSummary`, `sectionSummary`, and `chunk`.

#### Scenario: chunk has all required fields

Given a chunk produced by the ingestion pipeline
Then the chunk's serialized form contains every field listed above
And unknown fields are preserved unchanged across a round trip.

### Requirement: knowledge provenance state model

Every durable fact (chunk, entity, relation, evidence) MUST have a
`KnowledgeState` from the following set:

- `verified` — confirmed by direct source evidence;
- `inferred` — derived from another fact by a documented deterministic
  rule;
- `assumption` — proposed by a human operator or by an LLM worker
  with a documented prompt and never used as authoritative input to
  other rules without operator approval;
- `conflicting` — at least two verified/inferred facts disagree on
  a non-trivial aspect;
- `stale` — the source has changed and the fact has not yet been
  re-verified;
- `unknown` — provenance is not yet recorded.

The KnowledgeState of every durable fact MUST be inspectable in
the runtime working knowledge store and MUST be reported back in
MCP retrieval responses.

#### Scenario: stale fact is surfaced as stale

Given an entity derived from a CSV row that has since changed
When the platform re-checks the entity after the CSV is updated
Then the entity's previous `verified` fact becomes `stale`
And the runtime working knowledge store records the staleness with
a reference to the new source version.

### Requirement: OKF v0.2 Wiki profile conformance

The Wiki layer under `project-knowledge/wiki/` MUST be a profiled
Open Knowledge Format bundle. The bundle root `index.md` MUST
declare the targeted OKF version in its YAML frontmatter using
the key `okf_version: "0.2"`.

Every non-reserved concept Markdown file MUST contain parseable
YAML frontmatter and a non-empty `type` field. Platform-specific
extensions MUST use a stable project-specific prefix `pi_` so that
OKF readers ignore them while the platform retains richer provenance
metadata.

The reserved files `index.md` (progressive disclosure and
navigation) and `log.md` (chronological updates for the scope)
MUST be honoured.

Runtime binary artifacts (vectors, ANN indexes, sparse indices,
database pages, model caches) MUST NOT live inside the Wiki bundle
boundary.

#### Scenario: OKF v0.2 root index

Given a target project with a populated Wiki
When the platform writes the Wiki bundle root
Then `project-knowledge/wiki/index.md` starts with YAML frontmatter
declaring `okf_version: "0.2"` and `type: "WikiIndex"`.

#### Scenario: platform extension uses pi_ prefix

Given a Wiki concept Markdown file produced by the platform
When the file's frontmatter is read by a third-party OKF reader
Then the third-party reader ignores `pi_status`, `pi_source_hash`,
and `pi_project_version` because they carry the `pi_` prefix
And the third-party reader still sees the documented `type`,
`title`, `description`, `resource` and `tags` fields.

### Requirement: OkfAdapter isolates runtime model from OKF revision

The platform MUST implement an `OkfAdapter` that translates between
the internal Knowledge Model and the configured OKF profile/version.
The internal Knowledge Model MUST NOT be coupled to any specific
OKF minor version.

The platform MUST run an OKF conformance validation step before any
durable Wiki materialization. The validation MUST check at minimum:

- parseable YAML frontmatter on every non-reserved concept file;
- a non-empty `type` field on every such file;
- valid reserved filenames (`index.md`, `log.md`);
- root declared OKF version when configured;
- stable relative links where they are used;
- presence of platform provenance extensions where required;
- no accidental runtime/binary files inside the OKF bundle.

#### Scenario: invalid Wiki materialization is rejected

Given a Wiki concept Markdown file with missing `type` frontmatter
When the platform attempts to materialise it to durable canonical
knowledge
Then the materialisation step fails with a validation error
And no Git diff is produced.

### Requirement: internal knowledge model forward compatibility

The platform's internal Knowledge Model MUST be able to support a
future OKF v0.3+ revision without modifying domain code, by
exchanging only the `OkfAdapter` implementation.

#### Scenario: OKF version bump isolated to OkfAdapter

Given a future operator request to support OKF v0.3
When the platform is upgraded
Then only the `OkfAdapter` implementation changes
And no chunk, entity or relation definition changes.

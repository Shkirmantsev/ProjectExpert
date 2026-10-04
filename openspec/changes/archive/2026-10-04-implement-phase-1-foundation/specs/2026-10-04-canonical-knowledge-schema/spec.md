# canonical-knowledge-schema Specification delta (Phase 1 addendum)

This delta pins the concrete value types, content addressing,
manifest shape, OKF v0.2 profile, OKF conformance validator and
the property-based round-trip test that the Phase 1 implementation
delivers under `platform/core/canonical/`. The base specification
in
[`openspec/specs/2026-10-04-canonical-knowledge-schema/spec.md`](../../../../specs/2026-10-04-canonical-knowledge-schema/spec.md)
remains authoritative for the platform-level contract.

## ADDED Requirements

### Requirement: concrete value-type catalogue

The Phase 1 implementation MUST expose the following value types
as concrete Python dataclasses in `platform/core/canonical/
value_types.py`:

- `Source`, `Document`, `Section`, `Chunk`, `ContextualChunk`,
  `Entity`, `Relation`, `Evidence`, `KnowledgeState`,
  `ProjectVersion`, `Shard`, `Manifest`, `RuntimeChange`,
  `TaskContext`, `Metadata`.

Every value type MUST implement a deterministic JSON serializer
(`to_canonical_json`) that produces byte-identical output for two
in-memory instances that carry the same logical state.

#### Scenario: every value type round-trips through the serializer

Given an instance of every Phase 1 value type constructed with
deterministic field values
When each instance is serialised via `to_canonical_json` and then
parsed back via `from_canonical_json`
Then the parsed instance is structurally equal to the original.

### Requirement: chunk content address

The Phase 1 implementation MUST expose
`pi_platform.core.canonical.content_address.content_address(...)` that
computes the SHA-256 hex digest of the canonical JSON serialization
of the chunk body (without `metadata`, `entityIds`, `parentId`,
`childIds`).

#### Scenario: equivalent chunks share the same content address

Given two `Chunk` instances with the same `rawText` but different
`metadata` values
When `content_address` is called on each
Then both calls return the same SHA-256 hex digest.

### Requirement: manifest content schema

Per-family manifests MUST be serialised as JSON with the keys
`schemaVersion`, `family`, `shards` (list of `{id, path,
contentHash, sourceHash, count}`) and `dependencies` (list of
manifest identifiers). The manifest MUST carry a `contentHash` for
itself, computed from the canonical JSON serialization of the
manifest body.

#### Scenario: manifest self-hash is stable

Given a manifest with N shards
When the manifest is serialised twice with the same shard list
Then both serialisations produce the same manifest `contentHash`.

### Requirement: OKF v0.2 adapter implementation

The Phase 1 implementation MUST expose
`pi_platform.core.canonical.okf.OkfAdapter` (abstract) and
`pi_platform.core.canonical.okf.OkfV02Profile` (concrete). The profile
MUST:

- parse YAML frontmatter from a Markdown string using the standard
  library `yaml.safe_load` only;
- validate that `project-knowledge/wiki/index.md` carries
  `okf_version: "0.2"` and `type: "WikiIndex"`;
- validate that every non-reserved concept Markdown file under
  `project-knowledge/wiki/` has YAML frontmatter and a non-empty
  `type` field;
- treat fields whose key starts with `pi_` as platform extensions
  and ignore them when checking for OKF compliance;
- reject runtime/binary files inside the Wiki bundle boundary.

#### Scenario: OKF v0.2 profile rejects missing type

Given a concept Markdown file with parseable YAML frontmatter but
no `type` field
When `OkfV02Profile.validate_file(...)` is called
Then it returns an error naming the missing `type` field.

#### Scenario: OKF v0.2 profile ignores pi_ fields

Given a concept Markdown file with `pi_status`,
`pi_source_hash`, `pi_project_version` and the documented OKF fields
When a third-party OKF reader parses the frontmatter
Then it reports `type`, `title`, `description`, `resource` and
`tags` are present
And it does not report the `pi_` fields.

### Requirement: property-based round-trip test

The Phase 1 implementation MUST include a property-based test in
[`tests/test_canonical_roundtrip.py`](../../../../../tests/test_canonical_roundtrip.py)
that asserts byte-identical canonical serialization for at least
100 random instances of each value type.

#### Scenario: equivalent states produce byte-identical files

Given two equivalent in-memory states of `Chunk`, `Entity`,
`Relation`, `Manifest` and `Metadata` constructed via shuffled
insertion order
When each state is serialised to canonical JSON
Then the two `bytes` objects are equal.
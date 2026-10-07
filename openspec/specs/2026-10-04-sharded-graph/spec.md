# 2026-10-04-sharded-graph Specification

## Purpose
Store and retrieve knowledge graph entities and relations in content-addressed shards with reproducible manifests.
## Requirements
### Requirement: GraphPort contract

The platform MUST expose a `GraphPort` abstract class in
`pi_platform/ports/runtime/graph.py` with the following operations:

- `upsert_entity(entity: Entity) -> None` — keyed by `Entity.id`,
  atomic across files;
- `upsert_relation(relation: Relation) -> None`;
- `get_entity(entity_id: str) -> Optional[Entity]`;
- `get_relations(entity_id: str, *, edge_type: Optional[str] =
  None, direction: str = "outgoing") -> Sequence[Relation]`;
- `shard_by(content_hash: str) -> Shard` — returns the shard that
  owns the content address (mod 256 hash-prefix shard);
- `rebuild_manifest() -> GraphManifest` — regenerates the §10.3
  graph manifest from the on-disk shards.

#### Scenario: upsert and read round-trip an entity

Given an entity `e-1` with `family="Component"` and
`name="PackingService"`
When `upsert_entity(e-1)` runs followed by `get_entity("e-1")`
Then the returned entity equals the original entity byte-for-byte.

### Requirement: hash-prefix shard layout

The default `ShardedGraph` adapter MUST use the §10.1 hash-prefix
shard layout (`graph/nodes/00/`, `graph/nodes/01/`, …,
`graph/nodes/ff/` and `graph/edges/00/`, …, `graph/edges/ff/`) so
the per-shard file count stays bounded under load.

#### Scenario: shard_by returns the hash-prefix shard

Given a content address whose first two hex characters are `ab`
When `shard_by(content_hash)` runs
Then the returned shard directory is `graph/nodes/ab/`.

### Requirement: 32 MiB per-file cap

Every shard directory MUST hold at most one entities file
(`entities.jsonl.gz`) and one relations file (`relations.jsonl.gz`);
the gzipped JSONL files MUST cap at 32 MiB uncompressed so a
contributor can inspect any single shard file with a stock editor.

#### Scenario: 50 000-entity property test respects the per-file cap

Given a fixture with 50 000 entities distributed across the hash-
prefix shards
When the sharded graph is built and the per-shard file sizes are
measured
Then no shard file exceeds 32 MiB uncompressed
And the shard count distribution matches the §10.1 hash-prefix
expectation.

### Requirement: content-addressed entity bodies

Every entity body MUST be stored by its SHA-256 content address
under `objects/<prefix>/<hash>.json` so identical entity bodies
across branches share one canonical artefact.

#### Scenario: identical entity bodies share one canonical artefact

Given two entities with identical bodies but different `id`s
When both are written via `upsert_entity`
Then the canonical artefact under
`objects/<prefix>/<hash>.json` is shared between the two
entities
And the graph reports a single cache hit on the second write.

### Requirement: knowledge graph vs. ANN graph separation

The `GraphPort` MUST operate only on the knowledge graph (§17
invariant); the ANN graph is owned by the `DenseIndexPort`. The two
graphs MUST NOT be confused: the knowledge graph has no notion of
vector similarity; the ANN graph has no notion of `Entity` or
`Relation` families.

#### Scenario: ANN vectors are not visible from the knowledge graph

Given an `Entity` whose `id` is `e-1`
When the knowledge graph is queried for `e-1`
Then the graph returns the entity and its relations
And the graph does not return the entity's embedding vector.

### Requirement: GraphManifest generation

Every call to `rebuild_manifest` MUST regenerate the §10.3 graph
manifest with the shard IDs, paths, content hashes, source hashes,
schema version, entity counts and shard dependency list so the
runtime hydration can operate from the manifest.

#### Scenario: manifest reflects the current shard state

Given a sharded graph over 1000 entities
When `rebuild_manifest()` runs
Then the manifest lists every shard directory
And the manifest's entity count equals 1000
And the manifest's content hash list matches the canonical artefact
list under `objects/<prefix>/`.

### Requirement: Entity and Relation families from §16

The graph MUST accept every entity family from §16
(`Requirement`, `Specification`, `OpenSpecChange`, `ADR`,
`BusinessConcept`, `Component`, `Module`, `JavaClass`,
`JavaMethod`, `Interface`, `API`, `Dependency`, `DatabaseTable`,
`Protocol`, `Test`, `DocumentationSource`, `Document`, `Section`,
`Chunk`) and every relation family from §16 (`IMPLEMENTS`,
`SATISFIES`, `DEPENDS_ON`, `CALLS`, `USES`, `IMPLEMENTED_BY`,
`DEFINED_BY`, `PART_OF`, `DOCUMENTED_BY`, `TESTED_BY`,
`REFERENCES`, `SUPERSEDES`, `DESCRIBES`).

#### Scenario: every entity family round-trips through the graph

Given one entity per family from §16
When every entity is upserted and read back
Then the round-trip preserves the family label for every entity.


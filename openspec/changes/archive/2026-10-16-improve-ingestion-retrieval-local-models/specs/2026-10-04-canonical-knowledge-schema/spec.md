# 2026-10-04-canonical-knowledge-schema Specification delta

Covers plan §3.2, §19, §20, §22. The existing
canonical-knowledge-schema `Requirements` remain unchanged;
this delta adds the additive rich-document types and the
`Chunk.anchors` field.

## ADDED Requirements

### Requirement: additive rich document graph

The canonical knowledge schema MUST support an additive
rich document submodel. The new types (`DocumentRevision`,
`Page`, `DocumentElement` and its `Heading` / `Paragraph` /
`List` / `Table` / `Figure` / `Formula` variants,
`ElementKind`, `SourceAnchor`, `AssetRef`, `TableGrid`,
`IngestionCheckpoint`) MUST be project-neutral, MUST NOT
import Docling (or any other vendor) types, and MUST be
projected into the existing generic public model
(`Document`, `Section`, `Chunk`, `Entity`, `Relation`,
`Evidence`).

#### Scenario: PDF source projects into the generic model

Given a 10-page PDF ingested through the
`DoclingPdfAdapter`
When the platform materialises the canonical knowledge
Then every page element is represented as a `Section`
or `Chunk` and every figure is represented as an
`AssetRef` and an `Entity`
And no Docling type appears in any canonical artifact.

### Requirement: Chunk carries SourceAnchor list

`Chunk` MUST carry an additive optional
`anchors: Sequence[SourceAnchor]` field. Legacy chunks
without `anchors` MUST continue to deserialize and
participate in retrieval unchanged; for them, the
`anchors` list is empty.

#### Scenario: legacy chunk deserialises with empty anchors

Given a hydrated target project with only legacy chunks
When the platform reads a legacy chunk
Then the chunk is deserialised with an empty
`anchors` list
And the chunk is queryable through the existing
retrieval pipeline with no behavioural change.

### Requirement: knowledge schema version 2 migration

The platform MUST bump `KNOWLEDGE_SCHEMA_VERSION` from
`1` to `2` to record the additive rich-document types
and the new `Chunk.anchors` field. The migration MUST
be additive and reversible.

#### Scenario: v1 → v2 migration preserves legacy data

Given a hydrated `runtime.db` at schema `1`
When the platform runs the v1 → v2 migration
Then existing rows are preserved
And new fields default to empty
And the down migration restores the v1 schema and is
rejected if any v2 record exists.

## MODIFIED Requirements

None. The existing canonical-knowledge-schema
`Requirements` (deterministic canonical serialisation,
canonical object content addressing, sharded canonical
storage, manifest per family, …) are not modified by
this delta. The new types are layered on top of the
existing model and never change the serialisation of
legacy records.

# rich-document-graph Specification delta

Covers plan §3.2, §19, §19.1, §20, §22.

## Purpose

Define an additive, ProjectExpert-neutral rich-document
submodel (`DocumentRevision`, `Page`, `DocumentElement`,
`ElementKind`, `SourceAnchor`, `AssetRef`, `TableGrid`,
`IngestionCheckpoint`) layered on top of the existing canonical
`Document` / `Section` / `Chunk` / `Entity` / `Relation` /
`Evidence` model. The rich submodel is projected into the
existing generic types and is the source of truth for
page-level provenance, tables, figures, formulas, OCR
provenance, binary assets, and the relation of a chunk to
source elements. Docling types must not leak past the
adapter boundary.

## ADDED Requirements

### Requirement: additive rich-document types

The canonical knowledge schema MUST define the additive
types `DocumentRevision`, `Page`, `DocumentElement`
(discriminated union of `Heading`, `Paragraph`, `List`,
`Table`, `Figure`, `Formula`), `ElementKind`, `SourceAnchor`,
`AssetRef`, `TableGrid`, `IngestionCheckpoint`.

`Chunk` MUST gain an additive optional field
`anchors: Sequence[SourceAnchor]`. Existing chunks without
`anchors` MUST continue to deserialize and participate in
retrieval unchanged.

#### Scenario: legacy chunks remain valid

Given an existing chunk with no `anchors` field
When the platform ingests the chunk
Then the chunk is deserialised with an empty `anchors` list
And the chunk is queryable through the existing retrieval
pipeline with no behavioural change.

#### Scenario: rich document graph round-trips

Given a PDF source ingested through the new
`DoclingPdfAdapter`
When the platform serialises the canonical knowledge for
that source
Then `document_revisions`, `pages`, `document_elements`,
`assets`, and `chunk_anchors` records are produced
And the bytes are byte-identical across two runs with the
same source bytes and the same parser version.

### Requirement: deterministic rich-document IDs

The platform MUST compute the following IDs deterministically
for the rich-document submodel:

- `source_id = sha256(canonical(normalized source URI))`
- `revision_id = sha256(file bytes)`
- `element_id = sha256(revision_id || page || element kind
  || canonical(geometry) || content hash)`
- `asset_id = sha256(asset bytes)`
- `chunk_id = sha256(chunker_strategy_version || ordered
  source anchors)`

The platform MUST also retain a non-authoritative
`semantic_key = heading_path || element_kind || local_ordinal`
on `DocumentElement` for cross-revision matching; the
`semantic_key` MUST NOT replace the deterministic
`element_id` as the primary key.

#### Scenario: identical bytes produce identical revision_id

Given the same PDF bytes ingested twice
When the platform resolves the `revision_id`
Then both calls return the same `revision_id`.

#### Scenario: moved element shares semantic_key but not element_id

Given a heading that is moved to a different page in a
new revision
When the platform compares the two revisions
Then the `semantic_key` is preserved across revisions
And the `element_id` differs.

### Requirement: source anchor projection

The platform MUST add `SourceAnchor`
(`revision_id`, `page`, `element_id`, `bbox`, `line`,
`asset_id`) to `Chunk` as an additive `anchors` sequence.
The anchor MUST be sufficient to point from a retrieval hit
back to the exact page, element, geometry, and (for figures)
asset of the original document.

#### Scenario: PDF retrieval hit points to original page

Given a chunk produced by the PDF ingestion pipeline
When the chunk is returned as a retrieval hit
Then the hit's `source_anchor` resolves to a specific page
and `element_id` of the original `DocumentRevision`.

### Requirement: schema migration is additive and reversible

The platform MUST bump `KNOWLEDGE_SCHEMA_VERSION` from
`1` to `2` to record the additive rich-document types and
the new `Chunk.anchors` field. The migration MUST be
additive and reversible: legacy records are not rewritten;
new fields default to empty. The `down` migration MUST
remove the new tables/columns and decrement the version,
but only if no v2 records exist.

#### Scenario: legacy knowledge base migrates without data loss

Given a hydrated `runtime.db` with no `anchors` and no
`document_revisions` table
When the platform runs the v1 → v2 migration
Then the existing rows are preserved
And the new fields default to empty
And the `down` migration restores the v1 schema and is
rejected if any v2 record exists.

## MODIFIED Requirements

None. The existing canonical-knowledge-schema
`Requirements` (deterministic canonical serialisation,
canonical object content addressing, sharded canonical
storage, manifest per family, …) remain unchanged. The
additive types are layered on top and never change the
serialisation of legacy records.

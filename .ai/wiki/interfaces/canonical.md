---
id: interfaces.canonical
title: Canonical interface reference
kind: interfaces
status: active
summary: Reference for the canonical value types, content addressing, manifest I/O and OKF v0.2 profile implemented by Phase 1.
sourceRefs:
  - pi_platform/core/canonical/value_types.py
  - pi_platform/core/canonical/serializer.py
  - pi_platform/core/canonical/content_address.py
  - pi_platform/core/canonical/manifest.py
  - pi_platform/core/canonical/okf.py
  - openspec/specs/2026-10-04-canonical-knowledge-schema/spec.md
maintenance:
  mode: authored
---

# Canonical interface reference

Implements the
[`canonical-knowledge-schema`](../../../openspec/specs/2026-10-04-canonical-knowledge-schema/spec.md)
spec.

## Value types

`pi_platform.core.canonical.value_types` exposes the Phase 1
value types as frozen dataclasses:

| Type | Required fields | Notes |
|---|---|---|
| `Source` | `id`, `family`, `uri`, `contentHash` | Metadata envelope |
| `Document` | `id`, `title` | Sections optional |
| `Section` | `id`, `heading`, `level` | Optional `parentId` |
| `Chunk` | `id`, `rawText`, `contextualText`, `metadata`, `sourceReference`, `contentHash` | Optional `parentId`, `childIds`, `entityIds`, `provenance` |
| `ContextualChunk` | `chunk`, `contextPrefix` | Deterministic prefix |
| `Entity` | `id`, `family`, `label` | Optional relations and `knowledgeState` |
| `Relation` | `sourceId`, `targetId`, `family` | Optional `weight`, `evidence`, `knowledgeState` |
| `Evidence` | `knowledgeState`, `parserVersion` | Optional `sourceHash`, `lastVerifiedAt`, `rationale` |
| `ProjectVersion` | `gitHead`, `workingTreeFingerprint`, `knowledgeSchemaVersion`, `embeddingModelVersion`, `indexSchemaVersion` | Immutable identity tuple |
| `Shard` | `id`, `path`, `contentHash` | Optional `sourceHash`, `count` |
| `Manifest` | `schemaVersion`, `family` | Optional `shards`, `dependencies`, `contentHash` |
| `RuntimeChange` | `id`, `kind`, `payload`, `source` | Optional `knowledgeState` |
| `TaskContext` | `taskId`, `goal`, `budgetTokens` | Optional chunks/entities/OpenSpec IDs/requirements |
| `Metadata` | `documentId`, `version`, `language` | Optional fields per §23; `validate()` enforces `validFrom <= validTo` |

## Serialization

`pi_platform.core.canonical.serializer` provides `canonical_dump_json`,
`canonical_load_json`, `canonical_dump_yaml`, `canonical_load_yaml`
plus `normalize_identifier_list`, `normalize_str`,
`normalize_optional_str`. The serializers enforce:

- sorted mapping keys;
- canonical line endings (`\n`);
- trailing newline at end of file;
- stable identifier-array ordering (sorted ascending by string).

## Content addressing

`pi_platform.core.canonical.content_address` exposes
`content_address_bytes(raw)`, `content_address(value)` and
`object_path(content_hash)`. Every canonical immutable object is
addressed by its SHA-256 hex digest of its deterministic
canonical serialization. The runtime working knowledge cache uses
this digest as the primary key.

## Manifest I/O

`pi_platform.core.canonical.manifest` provides
`manifest_from_shards(family, shards, ...)`, `save_manifest(path,
manifest)` and `load_manifest(path)`. Manifests carry a
self-hash; the loader recomputes the hash against the body with
the `contentHash` field removed and raises `ManifestError` on a
mismatch.

## OKF v0.2

`pi_platform.core.canonical.okf` exposes `OkfAdapter` (abstract),
`OkfV02Profile` (concrete), `OkfValidationError`,
`parse_frontmatter`, and `validate_wiki_bundle`. The profile:

- parses YAML frontmatter via PyYAML (with a minimal YAML subset
  fallback when PyYAML is unavailable);
- validates that the Wiki root `index.md` declares
  `okf_version: "0.2"` and `type: "WikiIndex"`;
- validates that every non-reserved concept file under
  `project-knowledge/wiki/` has YAML frontmatter and a non-empty
  `type` field;
- treats fields whose key starts with `pi_` as platform
  extensions and ignores them when checking OKF compliance;
- rejects non-Markdown binary files inside the Wiki bundle.

## Failure and recovery

- Manifest hash mismatch raises `ManifestError`. Hydrate surfaces
  the error and continues with the next family so a single
  corrupted shard cannot block startup.
- The serializer never embeds volatile data; the only place
  timestamps appear is in the optional SBOM `creationInfo`
  field, which is regenerated at every build.
- The OKF validator never modifies the file system; it returns
  a list of errors and the caller decides what to do.
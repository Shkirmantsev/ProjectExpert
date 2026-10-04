---
id: adr.canonical-runtime-separation
title: Canonical knowledge and runtime working knowledge are distinct
kind: adr
status: accepted
summary: Keep Git-versioned canonical knowledge strictly separate from the runtime working knowledge store and require deterministic bidirectional synchronization.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md
  - openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/specs/canonical-knowledge-schema/spec.md
  - openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/specs/bidirectional-canonical-runtime-sync/spec.md
maintenance:
  mode: authored
---

# Canonical knowledge and runtime working knowledge are distinct

## Context

The v0.8 architecture (sections §5–§8, §62, §63, §68) requires two
distinct representations of project knowledge: durable, Git-versioned
canonical knowledge under `project-knowledge/`, and the optimised
runtime working knowledge store under `.project-intelligence-cache/`.
The two representations have different access patterns, different
lifecycles, different storage technologies and different visibility
rules. They must remain synchronisable in both directions without
losing durable information.

## Decision

The platform will implement the canonical and runtime representations
as two physically separate stores with a documented bidirectional
synchronisation contract (hydrate / reconcile / materialise) implemented
behind stable interfaces. The canonical tree MUST be the only durable
source of truth; the runtime store MUST be rebuildable from the
canonical tree at any time.

Canonical artefacts MUST be deterministically serialisable and
content-addressed by SHA-256. Materialisation is approval-gated.
Runtime binary artefacts (database pages, vector indexes, ANN indexes,
model caches) MUST NOT be committed to the target repository.

## Alternatives considered

- A single monolithic Git blob representing the entire runtime state.
  Rejected because it breaks clone/checkout performance, causes merge
  conflicts and produces large binary files in the Git tree.
- Using the runtime store as the source of truth and reconstructing
  canonical knowledge only at materialise time. Rejected because it
  couples durability to runtime availability and complicates
  multi-developer workflows.
- Storing the runtime store in Git. Rejected because it forces the
  Git tree to grow unboundedly and prevents incremental
  reconciliation on branch switch.

## Consequences

- `project-knowledge-repository-layout`, `canonical-knowledge-schema`,
  `git-version-aware-runtime` and `bidirectional-canonical-runtime-sync`
  Phase 1 specs depend on this separation.
- The runtime store requires a write-ahead log for crash-safe
  materialisation recovery.
- Round-trip reproducibility tests must be part of the regression suite.

## Verification

`openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md`
(`plan-v0-8-platform-architecture` change) defines the Phase 1
foundation implementation tasks including the round-trip test (task
39 in the Phase 1 section, `tests/test_sync_roundtrip.py`) and the
canonical serialization round-trip property test (task 22,
`tests/test_canonical_roundtrip.py`).
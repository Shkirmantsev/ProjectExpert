---
id: architecture.resumable-indexing
title: Resumable production indexing
kind: architecture
status: active
summary: Default SQLite source checkpoints, generation readers and resumable artifacts with explicit production release limits.
---

# Resumable production indexing

Observed implementation is explained in the
[operator guide](../../../docs/PRODUCTION_INDEXING_RESUME.md), with the proposed
contract under [implement-production-indexing-resume](../../../openspec/changes/implement-production-indexing-resume/proposal.md).
Accepted current requirements remain in [OpenSpec CURRENT](../../../openspec/CURRENT.md).

The coordinator returns an unpublished candidate. A single builder holds the OS
cache lock; a monotonically increasing SQLite fence guards source commits and
caller-owned publication. Source-local buffers publish payload, ownership and
summary in one FULL-synchronous transaction. Generation membership, rather than
unscoped cache dictionaries, selects source records. Immutable record hashes
include metadata; payload and source-summary checksums are checked on reads.

Exact FTS batches and deterministic graph shards resume independently. Vector
batches use the existing profile namespaces. Prior artifacts and legacy input
remain retained; no automatic GC or silent legacy fallback runs. SQLite backup
and journaled restore operate on generated state, never canonical sources.

Fresh source and kit defaults now use resumable indexing, parallel parsing and
bounded embedding batches; explicit legacy settings remain supported. Existing
operator environments remain preserved, with an explicit preview/backup migration. Source deployment now requires
verified offline asset seeding and fails closed when release pins/files are
missing. The licensed inventory is reviewed; published registry identity remains blocked;
[release assembly](../../../distribution/assets/README.md) records the workflow.
Full offline OCI asset release,
hardware acceptance, automatic artifact GC
and stale-version-safe last-good UI serving remain unverified or unimplemented;
the operator guide enumerates these differences from the supplied full design.
Do not infer production performance or complete release readiness from unit tests.

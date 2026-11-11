---
id: architecture.resumable-indexing
title: Resumable production indexing
kind: architecture
status: active
summary: Opt-in SQLite source checkpoints, generation readers and resumable artifacts with explicit production release limits.
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

The default engine remains legacy during rollout. Full offline OCI asset release,
hardware acceptance, automatic artifact GC
and stale-version-safe last-good UI serving remain unverified or unimplemented;
the operator guide enumerates these differences from the supplied full design.
Do not infer production performance or complete release readiness from unit tests.

# Design

Reference: user-supplied Production Indexing Resume Performance Design V2,
2026-11-11; implementation follows its authoritative Appendix A over conceptual
schema examples. Work is on feature/generate-init-project, not document's dev.

## Boundaries
Keep public index_repository signature and runtime.extra. Caller still validates
snapshot and publishes; coordinator returns an unpublished candidate. Source
workers use isolated buffers; one locked connection serializes atomic commits.
Canonical reads are streamed through generation membership, never _store shims.
Use OS advisory exclusion plus monotonically increasing database fences. Keep
legacy ingestion.json intact and back it up before one-time transactional import.
Metadata, pipeline key and source content hash are independent reuse dimensions.

## Artifacts
FTS builds bounded idempotent batches into a candidate database. SQLite backup,
integrity/count validation, close, fsync and same-volume replacement produce a
standalone artifact. Graph shards use deterministic atomic per-shard files and
checksums; interrupted shards are reconciled before reuse. Dense vectors retain
existing profile namespaces. Completed vector batches survive failed ANN builds.

## Concurrency and failures
Parallel work admits bounded source tasks and CPU capacity, excludes shared PDF
handles, and applies backpressure. A source failure blocks complete publication
unless explicitly allowed by the operator. DB corruption, disk errors, immutable
address conflicts and stale fences fail closed; state is never deleted to retry.

## Rollout
PI_INDEX_ENGINE=legacy|resumable is explicit, without silent fallback. Keep new
engine opt-in until migration/restore and packaged SQLite release proof pass.
PI_INDEX_PARALLEL and PI_EMBED_BATCHING stay individually gated. Offline asset
requirements cannot be enabled by default until a real pinned pack is published.
No test fixture or fake embedding is evidence of actual hardware throughput.

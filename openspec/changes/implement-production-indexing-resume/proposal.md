# Production indexing recovery and throughput

## Why
Completed ingestion currently reaches disk only after all derived indexes finish.
A crash can repeat parsing; per-vector calls and per-document FTS transactions
also prevent useful batching on large repositories. The supplied production V2
design identifies these failures and requires compatibility with existing setup,
public index_repository(), snapshot publication and persisted vector namespaces.

## What changes
Introduce an explicit resumable engine with atomic per-source SQLite checkpoints,
generation-filtered streaming reads, exclusive builders, durable stage progress,
resumable bulk exact/graph artifacts, and preserved legacy migration/rollback.
Batch embeddings, bound parallel source work, preserve degraded parser evidence,
and add verified offline asset and enterprise trust deployment support.

## Affected capabilities
Ingestion pipeline driver, semantic index service, document source adapters,
resumable document ingestion, portable inference runtime and one-click distribution.
PR24 follow-up also repairs production capability model resolution and BM25-light
tie handling without lowering the real-model quality gates.
Current accepted specs remain authoritative until release gates are verified.

## Compatibility and release
Fresh source/kit defaults now select resumable indexing, parallel source parsing
and bounded embedding batches. Explicit legacy/serial settings remain available;
existing operator environments are preserved and migrated only by an explicit
backed-up command. Production promotion remains blocked until actual pinned-model,
restore and Windows/Rancher/Desktop release gates pass. No performance or hardware result is
inferred from architecture. External assets must have real hashes, licenses and
an immutable OCI release; absent release evidence is recorded as blocked.

The merge-time publication follow-up removes manual bootstrap: trusted CI
computes the reviewed inventory hash, reuses or builds/publishes compatible assets,
and binds the actual registry digest into the tested matching kit in the same run.
The source release JSON is an unbound template, not a manual approval bottleneck.

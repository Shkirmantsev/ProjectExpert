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
Current accepted specs remain authoritative until release gates are verified.

## Compatibility and release
Default switches remain conservative until actual pinned-model, restore and
Windows/Rancher/Desktop release gates pass. No performance or hardware result is
inferred from architecture. External assets must have real hashes, licenses and
an immutable OCI release; absent release evidence is recorded as blocked.

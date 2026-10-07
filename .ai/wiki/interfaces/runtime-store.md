---
id: interfaces.runtime-store
title: RuntimeStorePort interface
kind: interfaces
status: active
summary: Phase 3 RuntimeStorePort contract for the embedded runtime store.
sourceRefs:
  - pi_platform/ports/runtime/runtime_store.py
  - pi_platform/adapters/runtime/sqlite_runtime_store.py
maintenance:
  mode: authored
---

# RuntimeStorePort

The `RuntimeStorePort` abstract class is the documented contract
for the Phase 3 embedded runtime store. The default adapter is
`SqliteRuntimeStore` (Python stdlib `sqlite3`); the PostgreSQL
adapter is the opt-in enterprise-scale replacement.

## Operations

- `put(family: str, body: Mapping[str, Any]) -> str` — write a
  content-addressed entry. Returns the SHA-256 hex digest.
- `get(content_hash: str) -> RuntimeEntry` — read the entry.
- `has(content_hash: str) -> bool` — check the entry exists.
- `evict(content_hash: str) -> None` — drop the entry.
- `stats() -> Mapping[str, int]` — `entries`, `wal_tail_length`.
- `runtime_status(*, policy: KnowledgeStatePolicy = DURABLE) ->
  RuntimeStatusReport` — bound version, backend, cache entries, WAL
  tail length, families, family counts.
- `wal_tail_length() -> int` — current WAL tail length.
- `recover_wal() -> None` — replay the WAL after a crash.
- `backend_name() -> str` — `sqlite` or `postgres`.

## KnowledgeStatePolicy

- `DURABLE` (default) — exclude `local_only_chunk` facts.
- `ALL` — include every fact.
- `STALE` — include only stale facts.

## Storage layout

```text
.project-intelligence-cache/
├── runtime.db                      # SQLite database
├── wal.jsonl                       # write-ahead log
├── index.json                      # in-memory index mirror
└── objects/<prefix>/<hash>.json    # §10.2 content-addressed objects
```

## Cross-branch reuse

The runtime cache is keyed by SHA-256 content address so identical
artefacts across Git branches share one canonical entry.

## Concurrency

The store serialises mutation per target project via the Phase 1
advisory file lock. The SQLite backend uses `BEGIN IMMEDIATE` to
acquire the write-lock at the start of a mutation.

## CLI

- `python -m pi_platform.cli runtime-status` prints the
  `RuntimeStatusReport`.
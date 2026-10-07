---
id: adr.embedded-storage-selection
title: Phase 3 embedded storage engine selection
kind: adr
status: accepted
summary: PostgreSQL + SQLite dual-backend runtime store with Apache-2.0 / BSD licenses.
sourceRefs:
  - pi_platform/adapters/runtime/sqlite_runtime_store.py
  - pi_platform/ports/runtime/runtime_store.py
  - distribution/licenses/dependency-inventory.json
maintenance:
  mode: authored
---

# Embedded storage engine selection (Phase 3)

## Decision

Select a **PostgreSQL + SQLite dual-backend** for the Phase 3
runtime store. SQLite ships in the Python stdlib (`sqlite3`) and is
the default desktop profile; PostgreSQL is the opt-in
enterprise-scale replacement, gated on the `storage.backend:
postgres` configuration in `project-context.yaml` and a `LicenseGate`
pass for the `psycopg` Apache-2.0 driver.

## Rationale

The §61 constraint forbids Elasticsearch, Neo4j, Qdrant and
PostgreSQL for the *default* desktop deployment. SQLite covers the
default profile without an extra runtime dependency; PostgreSQL is
opt-in for the enterprise-scale profile.

Both backends expose the same `RuntimeStorePort` abstract class so
the rest of the platform stays backend-agnostic. The
`project-context.yaml:storage.backend` configuration value drives
the selection at `init-project` time.

## Rejected alternatives

- **DuckDB** (MIT) — strong analytical SQL, weak at concurrent
  writes. The runtime store is write-heavy (every Phase 2 ingestion
  appends to the WAL). Rejected for the default backend.
- **RocksDB** (Apache-2.0) — strong key-value performance, no
  relational queries, no full-text integration. Would require a
  second relational engine alongside the KV store, violating the §61
  "one embedded engine" preference.
- **sled** (MPL-2.0) — embedded Rust KV store. Rejected for two
  reasons: (a) MPL-2.0 is on the Phase 1 `review` license list and
  would force every distribution ship to carry a per-file licence
  review; (b) no relational queries.
- **LevelDB** (BSD-3-Clause) — KV-only. Same relational-query gap
  as RocksDB. Rejected.
- **Badger** (Apache-2.0) — Go KV store; not embeddable from a
  Python adapter without a sidecar.

## License floor

All runtime storage libraries carry an SPDX identifier that passes
`LicenseGate` under the default `licensing.mode: strict`
configuration. GPL, AGPL, SSPL, Commons-Clause and `*-NC-*`
licenses are not in the runtime storage dependency inventory.

## Compatibility

The `RuntimeStorePort` is implementable by both backends without
leaking backend-specific details into the port surface. The Phase 1
`pi_platform/runtime/cache.py` stub is preserved as a thin shim that
delegates to the SQLite backend, and the public `put` / `get` /
`has` / `evict` / `stats` surface stays backward-compatible.
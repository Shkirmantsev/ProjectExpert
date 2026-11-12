# Tasks

- [x] Add atomic SQLite ingestion state, source buffers, generation reader and migration tests.
- [x] Integrate resumable repository coordinator, durable stages and exclusive builder.
- [x] Add resumable bulk exact/graph construction with integrity and restart tests.
- [x] Batch embedding cache misses, transport and persistence with profile validation.
- [x] Add bounded source concurrency, parser fallback, encoding and Office routing.
- [x] Add offline asset verification/seeding, strict trust handling and liveness probes.
- [x] Review integration, run focused regressions and python harness.py check; fix failures.
- [x] Update Wiki/ADR/operator evidence and commit focused changes.
- [ ] Run packaged SQLite, real-model offline, hardware benchmark, kill/power-loss and Windows Rancher/Desktop release matrix before adoption.

## Mandatory offline release remediation
- [ ] Materialize exact pinned production assets and independently review per-file redistribution evidence.
- [x] Require verified local assets for standard setup, PDF/tokenizer/torch consumers and native Windows execution.
- [x] Require seed before model setup/startup, preserve upgrade settings and diagnose stale pins.
- [x] Add production publication gates for real network-denied seed/model/PDF/text/image/restart smoke.
- [ ] Execute that complete real offline production acceptance with a reviewed pack.
- [ ] Publish reviewed asset OCI image and record actual immutable image/manifest identities.

---
id: adr.0035-safe-source-projection-and-restore-only
title: Complete safe source projection and strict restore-only orchestration
kind: adr
status: accepted
summary: Reuse the indexer and signed writer with source-level admission, exact-byte media reviews and strict no-computation restore.
sourceRefs:
  - pi_platform/adapters/orchestration/knowledge_sync.py
  - pi_platform/adapters/sync/safe_export_projector.py
  - pi_platform/adapters/pdf/portable_assets.py
maintenance:
  mode: authored
---

# Complete safe source projection and strict restore-only orchestration

Use complete eligible source outputs rather than sanitizing identity-bearing
payloads. Propagate owner/reference/provenance denials in a disk-backed catalog.
Optional v2 scope metadata labels subset coverage without weakening membership.
Unknown media needs exact-byte operator review because text detectors cannot
classify pixels. Reviewer grants cannot override detector/policy denial.

Restore shares the resumable candidate builder while prohibiting parser scheduling
and new embedding requests. Incomplete inputs retain checkpoints and activation.
Reindex may reject bad Git cache inputs and calculate locally; verify stays strict.
UI authorization signs server-side requests. Local publication precedes optional
Git-file export and survives its failure.

Keep PDF figure provenance and exact vector projection hashes as text. Rebuild
missing crops by page only with matching source/render identities. Private SQLite
and CAS remain working stores. Old generated objects need separate safety auditing
and owner-reviewed cleanup. No destructive migration is required.

See [operator evidence](../../../docs/SAFE_KNOWLEDGE_REMEDIATION.md). Physical hosts,
models, full document-store replication, query ACLs and encrypted backups remain
separately verified deployment concerns.

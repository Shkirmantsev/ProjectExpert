---
id: adr.0034-portable-production-canonical-snapshots
title: Portable production snapshots remain distinct from local runtime state
kind: adr
status: accepted
summary: Project immutable production source results into verified bounded text, import before parsing, and preserve signed publication and caller-owned index activation.
sourceRefs:
  - pi_platform/adapters/sync/portable_format.py
  - pi_platform/adapters/sync/portable_snapshot_exporter.py
  - pi_platform/adapters/sync/portable_snapshot_importer.py
  - pi_platform/core/orchestration/repository_indexing.py
maintenance:
  mode: authored
---

# ADR 0034: Portable production canonical snapshots

Date: 2026-11-14. Implementation is opt-in; deployment and scale certification
remain separate from local software acceptance.

## Decision

Keep three distinct representations: approved Git text; resumable SQLite source
results; and profile-scoped local vectors/index generations. Project only a
published generation. Verify every portable record and complete source membership
before importing inside the existing exclusive indexer/fenced transactions.
Share one verified plan across import stages. Pure text imports use bounded
64-source / 16 MiB commit groups with per-source savepoints; heavy parsing retains
its original independently durable checkpoints. Unchanged source/vector records
are not rewritten.
Candidate publication remains owned by the production caller.

Use portable/v2 source/payload/vector envelopes, immutable SHA256-named JSONL
segments and recursively bounded manifest pages. Replace manifests/portable-v2.json
last, after validating installed files. Retain old referenced files. Exact Git
attributes disable newline conversion only for generated v2 files. No binary
runtime state, model assets or source images enter canonical export.

Portable source identity is opt-in via a checked-out v2 root or an export policy.
Existing unconfigured caches keep absolute-path keys; enabling v2 deliberately
requires one new parse to establish relative identities and document/section
structure. Enrichment follows the same identity. Import cannot infer a reusable
source from runtime.db alone.

Default export is off. Review mode produces only a private proposal. Approved-auto
requires an operator-issued HMAC materialise capability with repository/action
scope and a validity window; it is verified before file writes and again before
root publication. A missing, expired, forged or incorrectly scoped capability
fails export while retaining the already published local query generation. Git
commit/push remain entirely outside the product.

## Consequences and limits

A cold clone with matching source bytes/pipeline reuses parsing. Optional exact
float32 textual vectors permit document-embedding reuse for matching profiles;
normal query/health embeddings remain expected. Source names must be portable,
source membership complete, and graph/document references resolvable. Restricted
source policy and security classes fail closed; denied co-owners deny a complete
source result. Known credential signatures are rejected; this is not a universal
secret detector and operator review remains necessary.

Cross-corpus ordering uses SQLite spooling; one source result is buffered up to
64 MiB. Every portable file has a declared 1–16 MiB production cap (default 8).
Budget limits fail rather than truncate. Private staging and immutable historical
files accumulate until explicitly reviewed; automatic GC is deliberately absent.

v1 remains readable without conversion. Strict hydration reports missing/corrupt
files and actual cold/warm hits; strict=False is an explicit legacy compatibility
mode. New exports cannot silently relocate parser-private figure assets or
reconstruct missing legacy source provenance. Managed workspace volume write-back
continues to require the existing synchronizer; this feature does not bypass it.

See the operator guide and evidence matrix for measured coverage and unexecuted
physical deployment/scale gates.

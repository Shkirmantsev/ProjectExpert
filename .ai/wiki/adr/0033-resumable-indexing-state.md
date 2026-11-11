---
id: adr.0033-resumable-indexing-state
title: Durable source checkpoints and isolated retrieval candidates
kind: adr
status: accepted
summary: Separate atomic source durability from derived artifact construction and caller-owned publication.
---

# ADR 0033: Durable source checkpoints and isolated retrieval candidates

Date: 2026-11-11. Scope: opt-in resumable engine implementation; production
rollout remains gated by the [operator guide](../../../docs/PRODUCTION_INDEXING_RESUME.md).

## Decision

Persist complete source results atomically in SQLite with FULL synchronous WAL,
immutable canonical bytes and generation-scoped membership. Keep each source's
uncommitted writes in a private buffer. Serialize short DB writes under one
exclusive builder and fence state transitions/publication. Preserve the public
indexer interface and caller ownership of snapshot activation.

Use complete serialized content hashes for immutable records. Legacy chunk body
projection keys omit metadata and may map to different full payloads over time;
they remain a legacy reuse mechanism, not an immutable payload identity.

Build exact and graph candidates independently with bounded checkpoints. Promote
only validated, closed standalone SQLite artifacts; keep stored vectors in their
existing profile namespace. Preserve input JSON and verified backups during
migration. Rollback is explicit, with no hidden legacy retry or cache deletion.

## Consequences

A late model failure no longer discards completed source parsing. Previous
candidate memberships and published artifacts stay intact. Additional SQLite
state and retained generations consume disk; free-space checks are preflight,
not storage guarantees. Default source concurrency uses bounded threads and
memory estimates; PDF remains serial to preserve connection ownership. Complete
packaged SQLite, hardware and OS release verification is still required.

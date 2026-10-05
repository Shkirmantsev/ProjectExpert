---
id: interfaces.freshness
title: FreshnessTrackerPort interface
kind: interfaces
status: active
summary: Per-fact freshness tracker with lastVerifiedAt timestamps.
sourceRefs:
  - pi_platform/ports/runtime/freshness.py
  - pi_platform/adapters/runtime/last_verified_freshness_tracker.py
maintenance:
  mode: authored
---

# FreshnessTrackerPort

The `FreshnessTrackerPort` abstract class records the per-fact
`lastVerifiedAt` timestamp and the `current_source_hash` so the
reconcile flow can replay the freshness delta without re-reading
every fact.

## Operations

- `mark_verified(fact_id, *, source_hash, version)` — record the
  `lastVerifiedAt` timestamp.
- `is_stale(fact_id, *, current_source_hash)` — return `True` when
  the fact's recorded `source_hash` differs from
  `current_source_hash`.
- `derived_staleness(derived_fact_id, *, depends_on)` — return
  `True` when any upstream fact is `stale` or `unknown`.
- `snapshot()` — return a `FreshnessSnapshot` that the reconcile
  flow can replay.

## Derived staleness rule

The port only marks a derived fact stale when an upstream fact is
`stale` or `unknown`. Derived facts do not become orphaned
evidence.

## Default adapter

`LastVerifiedFreshnessTracker` (SQLite-backed; records every
`mark_verified` call with the `lastVerifiedAt` timestamp and the
`source_hash`).

## §55 freshness contract compliance

The port follows the documented freshness flow:

```text
changed source
     ↓
dependency/provenance analysis
     ↓
affected knowledge
     ↓
mark stale / regenerate candidates
     ↓
verify
     ↓
materialize durable update
```

The port MUST NOT silently rewrite authoritative knowledge (§55
"avoid uncontrolled rewriting of authoritative knowledge").
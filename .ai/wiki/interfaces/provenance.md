---
id: interfaces.provenance
title: ProvenancePort interface
kind: interfaces
status: active
summary: KnowledgeState lifecycle and provenance chain.
sourceRefs:
  - pi_platform/ports/runtime/provenance.py
  - pi_platform/adapters/runtime/provenance_tracker.py
maintenance:
  mode: authored
---

# ProvenancePort

The `ProvenancePort` abstract class exposes the canonical
`KnowledgeState` lifecycle and the evidence chain for every durable
fact.

## Operations

- `transition(entity_id, *, from_state, to_state, evidence)` —
  atomic transition with the supplied evidence.
- `current_state(entity_id)` — return the current state.
- `evidence(entity_id)` — return the evidence records.
- `staleness_map()` — return the current state of every entity.

## State machine

```text
verified   ──→ inferred   (LLM-derived evidence; deterministic
                    unchanged)
inferred   ──→ stale      (source content changed; old evidence no
                    longer matches)
stale      ──→ verified   (re-derived evidence matches the new
                    source content)
stale      ──→ unknown    (source deleted; canonical snapshot gone)
verified   ──→ conflicting (parallel branch reports a different
                    authoritative value)
inferred   ──→ unknown    (LLM-disabled; no deterministic evidence
                    remains)
unknown    ──→ inferred   (new evidence becomes available)
```

## Default adapter

`LocalProvenanceTracker` (SQLite-backed state machine; enforces the
allowed transitions).

## Human vs. LLM distinction

- `verified` and `stale` MUST be reachable only from deterministic
  evidence.
- `inferred` MUST carry `LLM-derived: true`.
- `assumption` MUST carry `LLM-derived: true` and the `assumed_by`
  reference.
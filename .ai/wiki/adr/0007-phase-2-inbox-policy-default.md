---
id: adr.phase-2-inbox-policy-default
title: Default inbox sources to LOCAL_ONLY
kind: adr
status: accepted
summary: Default inbox sources to LOCAL_ONLY contracts and observed Phase 2 behavior.
sourceRefs:
  - pi_platform/adapters/ingest/local_pipeline_driver.py
  - tests/test_platform_phase2.py
maintenance:
  mode: authored
---

# Default inbox sources to LOCAL_ONLY

## Decision

Default local inbox sources to LOCAL_ONLY. Apply relative-path glob overrides using
the longest matching pattern; ties sort by pattern text. Policy values are uppercase
LOCAL_ONLY, REFERENCE and SNAPSHOT and survive canonical Source round trips.
LOCAL_ONLY chunks are unknown and cannot be promoted. REFERENCE chunks are assumptions
and promotion writes reference metadata only. SNAPSHOT promotion copies source bytes
and reference metadata only through an explicit operator call. Ingestion itself never
promotes sources. Source deletion marks runtime records stale and preserves snapshots.

The scanner skips files present in both Git HEAD and index, unsupported suffixes,
symlinks and sources over the 256 MiB default limit. Ordering follows relative paths.
The cache retains source ownership so invalidation does not remove another source's
shared records. The CLI persists local operational evidence under tmp/local; a
persistent runtime database is a Phase 3 capability.

[Ingestion](../modules/ingest.md) · [Source adapters](../interfaces/source-adapters.md)

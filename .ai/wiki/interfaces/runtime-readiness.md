---
id: interfaces.runtime-readiness
title: Knowledge readiness gate contract
kind: interfaces
status: active
summary: Phase 6 prerequisite 3 — every MCP tool consults KnowledgeReadinessPort before serving; RuntimeNotReadyError when hydrate / reconcile is inconsistent.
sourceRefs:
  - pi_platform/ports/__init__.py
  - pi_platform/core/sync/readiness.py
  - openspec/specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md
maintenance:
  mode: authored
related:
  - interfaces.mcp-tools
---

# Knowledge readiness gate contract

The `KnowledgeReadinessPort` is the trusted single source
of truth the MCP server (and any tool serving project
knowledge) consults before returning evidence.

## State machine

`ReadinessSnapshot.consistent` is True iff:

- a successful `HydrateReport` has been recorded;
- a successful `ReconcileReport` has been recorded;
- `failure_reason` is empty;
- `in_progress` is False.

## Failure modes

- "no hydrate recorded yet" — initial state.
- "no reconcile recorded yet" — after hydrate, before
  reconcile.
- "branch switch could not reconcile" — explicit
  `record_failure(...)` after a failed reconcile cycle.
- "in progress" — `begin_refresh()` was called and the
  refresh has not yet `end_refresh()`ed.

## Tool-side enforcement

Every MCP tool handler calls
`pi_platform.core.sync.readiness.assert_ready(readiness)`
before any data fetch. An inconsistent snapshot raises
`RuntimeNotReadyError` which the MCP server surfaces as a
typed error payload so the calling agent can branch
without parsing prose.

## Cross-version evidence

The gate's snapshot carries `current_head` and
`working_tree_fingerprint`. The MCP server cross-checks
the caller's requested evidence against the snapshot and
rejects attempts to serve evidence from a different
project version.
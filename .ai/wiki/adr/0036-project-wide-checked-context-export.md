---
id: adr.0036-project-wide-checked-context-export
title: Project-wide checked context export
kind: adr
status: accepted
summary: Keep complete confidential local and MCP context while exporting independently checked text under one project-wide policy.
sourceRefs:
  - pi_platform/adapters/sync/checked_context.py
  - pi_platform/adapters/ui/http_server.py
maintenance:
  mode: authored
---

# ADR0036: Project-wide checked context export

Status: accepted for the owner-requested implementation, 2026-11-15.

## Context
The owner rejected per-file permissions and manual paths. One outward rule must
apply to all discovered sources; safe parts of mixed files may be shared while
confidential context remains available locally and through ProjectExpert MCP.
This updates ADR0035's individual media-review UX. Complete source-cache identity,
source-wide restrictions and trusted publication remain in force.

## Decision
Keep local source outputs and private vectors untouched. Export complete eligible
source results as before. For content-level failures only, separately project
independent validated text fragments into content-addressed `context` envelopes.
Do not export graph edges, aggregate source summaries or opaque media vectors as
part of a filtered fragment. Policy restrictions, unknown provenance, untracked
sources and protected dependencies cannot be bypassed through text projection.
All media descriptors/text undergo the common checks; raw binaries are not exported.
Existing exact-byte human review remains compatible evidence for opaque vectors,
but the UI neither requests nor configures per-file reviews.

Verified context records expose provenance and projection identity. They never
enter the complete ingestion source cache. Full local sources take precedence;
current source changes or restrictions reject incompatible shared context. Shared
context remains separately identified evidence in the committed snapshot even
when its original private source is unavailable. Old readers fail closed on the
new record/scope; new readers still accept older complete snapshots.

Reuse a vector only when exact checked text matches its original embedding input;
rekey it to the checked projection identity. Missing or opaque vectors remain
local and restore reports missing work rather than invoking a model implicitly.
Export uses existing persisted chunks and a disk-backed spool, not OCR/inference.

Local loopback ownership permits signing without a UI password; configured tokens
remain mandatory. Host, Origin, Fetch-Site and peer checks protect tokenless actions.
Public host bindings cannot enable local signing through the managed deployment.

## Alternatives and consequences
Dropping a complete contaminated source loses separable safe facts. Editing its
cached summary would falsely certify an incomplete source as reusable. Separate
projections preserve the boundary with an additive, explicit format capability.
Automated recognition does not prove arbitrary business confidentiality; declared
policy and unavailable evidence remain conservative. Previously committed data
requires separate owner-reviewed Git-history cleanup and is not silently rewritten.

## Verification
Real SQLite/Git round trips, checked-text vector identity and tamper checks, source
policy/taint regressions, complete private-cache reuse and real MCP dispatch after
export, HTTP local/remote-origin boundaries, full harness and live UI delivery.

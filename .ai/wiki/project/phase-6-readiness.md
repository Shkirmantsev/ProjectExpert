---
id: project.phase-6-readiness
title: Phase 6 preparation and readiness review
kind: project
status: active
summary: Observed Phase 1–5 workflow and outstanding prerequisites for the proposed Phase 6 agent integration.
sourceRefs:
  - openspec/CURRENT.md
  - openspec/changes/archive/2026-10-07-prepare-phase-6-agent-integration/design.md
  - openspec/changes/archive/2026-10-07-implement-phase-6-agent-integration/tasks.md
  - pi_platform/core/sync/materialise.py
  - pi_platform/core/orchestration/query_orchestrator.py
  - pi_platform/core/orchestration/capability_discovery.py
  - pi_platform/core/orchestration/task_context.py
maintenance:
  mode: authored
related:
  - project.implementation-roadmap
  - architecture.platform-overview
  - interfaces.capability-discovery
---

# Phase 6 preparation and readiness review

Reviewed on 2026-10-06. Phases 1–5 have accepted specs, product source and
archived implementation changes. Phase 6 remains a proposed implementation:
canonical roadmap tasks 85–95 are unchecked, and no product MCP server,
canonical integration skill or released vendor package was implemented by
preparation. The existing `tools/mcp/project-context-mcp/` is the development
harness Wiki/code navigation server, separate from planned `pi_platform/mcp/`.

## Current workflow

Agents resume structured task state, route skills, retrieve selected Wiki/spec
and code evidence, and checkpoint decisions and verification. Product operations
use canonical Git knowledge, hydrate/reconcile a version-bound runtime store,
ingest configured sources, retrieve evidence through Phase 4, optionally
escalate through Phase 5, and assemble bounded task context. Durable changes
are intended to use the approval-controlled materialisation workflow. Adoption
and CURRENT updates follow implementation verification rather than preparation.

## Observed gaps before integration

The [proposed design](../../../openspec/changes/archive/2026-10-07-prepare-phase-6-agent-integration/design.md)
records the detailed mappings and prerequisites. Source review found:

- MaterialiseService checks nonempty approval tokens for REQUIRE_APPROVAL but
  does not validate their authenticity and does not explicitly reject DENY.
  The trusted write boundary requires a prerequisite fix and negative tests
  before enabling MCP materialisation or refresh. This review does not fix code.
- QueryOrchestrator.orchestrate has no filter/version parameter. Filtered
  retrieval must use the Phase 4 typed query; filtered L1/L2 must fail explicitly
  until a specified extension preserves eligibility through escalation.
- TaskContextBuilder.build takes a goal and retrieved evidence, not a mandatory
  requirement ID. Provenance uses evidence/current_state/staleness_map/events,
  not a lookup method; graph lookups need explicit version/security checks.
- Capability discovery reports server `0.8.0`, product MCP API `1.3.0`, knowledge
  schema `0.7.0` and OKF `0.2` by default, while package metadata is `0.1.0`.
  Release meanings need documentation; SDK and wire protocol versions are
  separate. Skill/distribution/adapter versions are future artifact metadata,
  and A2A is unavailable. Architecture example versions are not release defaults.

The readiness design preserves immutable skill version resources, whole-package
integrity, shared cross-vendor release identity and consistent hydrate before
serving knowledge. Official vendor schemas and real client install/uninstall
smoke tests still require implementation-time validation. These are proposed
contracts, not evidence of runtime success.

## Next iteration

Use the [implementation prompt](../../../docs/handoff/phase-6-implementation-prompt.md)
and [implementation tasks](../../../openspec/changes/archive/2026-10-07-implement-phase-6-agent-integration/tasks.md).
Keep preparation/review task completion separate from Phase 6 implementation
completion. Record actual checks as PASS, FAIL or NOT RUN; prerequisites are
not satisfied merely because prior regression counts were green.

## Review verification

The corrected preparation and implementation changes pass strict OpenSpec
validation; all-item validation reports 45 passed, 0 failed. Wiki validation
reports 48 documents and no issues. Licence and artifact-manifest gates pass;
the ten delta pairs are byte-identical, their artifact links resolve, and
canonical tasks 85–95 remain unchecked.

`PATH="$PWD/tmp/local/bin:$PATH" python3 harness.py check` passed the 334
repository tests across 27 modules but failed three harness MCP tests because
sandbox socket creation was denied. The affected MCP suite was rerun with
local socket access and all 10 tests passed. The original full invocation is
therefore recorded as FAIL under the sandbox, not retroactively relabelled PASS.
Evidence logs are local generated files under `tmp/local/phase-6-preparation-review-check.log`
and `tmp/local/phase-6-review-mcp-check.log`. Phase 6 runtime/vendor integration
tests are NOT RUN because their implementation remains future work.

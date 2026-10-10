---
id: modules.hooks
title: Phase 7 Hook Runtime module map
kind: module
status: active
summary: Phase 7 control-plane Hook Runtime module map covering the §59.6 lifecycle events, failure policies and correlation IDs.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-hook-runtime/spec.md
  - pi_platform/core/control/hooks.py
  - pi_platform/ports/control/hooks.py
maintenance:
  mode: authored
related:
  - interfaces.hook-runtime
---

# Phase 7 Hook Runtime module map

The Phase 7 control plane ships a Hook Runtime that fires on
the documented §59.6 lifecycle events with bounded timeout,
cancellation, structured result, correlation id, audit record
and the documented failure policies.

## Lifecycle events

The runtime fires on every documented §59.6 event:

```text
beforeIngestion / afterIngestion
beforeIndexUpdate / afterIndexUpdate
beforeRetrieval / afterRetrieval
beforeContextAssembly / afterContextAssembly
beforeMcpTool / afterMcpTool
beforeAgentDelegation / afterAgentDelegation
beforeMaterialization / afterMaterialization
onBranchSwitch / onProjectOpen / onProjectClose
```

The `SECURITY_SENSITIVE_EVENTS` set flags `beforeMcpTool`,
`beforeAgentDelegation` and `beforeMaterialization` as
security-sensitive. `OBSERVABILITY_EVENTS` flags the
`after*` variants. The default failure policy mirrors the
documented §59.7 mapping.

## Failure policies

The documented §59.7 failure policies:

```text
FAIL_OPEN
FAIL_CLOSED
WARN_ONLY
DISABLE_PLUGIN
```

Security-sensitive hooks fail closed; observability-only
hooks may fail open. The `_apply_failure_policy` helper
raises `HookTimeoutError` or `HookCancelledError` for
`FAIL_CLOSED`; `DISABLE_PLUGIN` transitions the offending
plugin to `failed` in the `PluginRegistry`; `WARN_ONLY`
records a warning and continues.

## Correlation IDs

Every dispatch carries a deterministic correlation id. The
correlation id chains policy, audit and hook records for a
single data-plane action. Cancellation propagates through
the same id.

## Wiring

- `attach_policy_engine(policy)` — consults the Phase 7
  Policy Engine before dispatching each hook payload;
  raises `DeniedError` or `ApprovalRequired` as documented.
- `attach_audit_log(audit_log)` — records an audit entry
  for every hook invocation through the typed
  `AuditRecord` value.

## Public surface

The public surface lives under
`pi_platform.core.control.hooks.DefaultHookRuntime`. The
port is `pi_platform.ports.control.hooks.HookRuntimePort`.
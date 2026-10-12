# hook-runtime Specification delta

## Purpose

Expose the Hook Runtime that fires on the documented lifecycle events with bounded timeout, cancellation, correlation id, audit record and the documented failure policies.

## Requirements


### Requirement: Hook Runtime fires the documented §59.6 lifecycle events

The Hook Runtime MUST fire on the documented §59.6 events:
`beforeIngestion`, `afterIngestion`, `beforeIndexUpdate`,
`afterIndexUpdate`, `beforeRetrieval`, `afterRetrieval`,
`beforeContextAssembly`, `afterContextAssembly`,
`beforeMcpTool`, `afterMcpTool`, `beforeAgentDelegation`,
`afterAgentDelegation`, `beforeMaterialization`,
`afterMaterialization`, `onBranchSwitch`, `onProjectOpen`,
`onProjectClose`. Every event MUST be dispatched with a
deterministic, unique `correlationId`. The runtime MUST
support the documented `HookDefinition` shape (`hook id`,
`plugin id`, `event`, `priority`, `timeout`, `permissions`,
`failure policy`, `configuration`, `version`).

#### Scenario: runtime dispatches beforeMcpTool with a deterministic correlationId

Given a plugin registers a `beforeMcpTool` hook
When the data plane invokes `project.search`
Then the runtime dispatches the hook
And the dispatched hook carries a unique
`correlationId` matching the data-plane call id
And the data-plane call continues.

### Requirement: Hook Runtime enforces bounded timeout, cancellation and bounded retries

Every hook invocation MUST honour the documented `timeout`.
A hook that exceeds the timeout MUST be cancelled with the
typed `HookTimeoutError` and the failure policy MUST be
applied. A hook that exceeds the timeout MUST NOT silently
deadlock the calling data-plane action. The runtime MUST
support bounded retries (`maxRetries` per `HookDefinition`);
retries beyond `maxRetries` MUST apply the failure policy
without further retry. The runtime MUST support external
cancellation through the typed `HookCancelledError`.

#### Scenario: timeout aborts a security-sensitive hook with FAIL_CLOSED

Given a `beforeMaterialization` hook with `timeout=10ms`
and `failurePolicy="FAIL_CLOSED"`
When the hook sleeps for 50 ms
Then the runtime raises `HookTimeoutError`
And the failure policy is applied (`FAIL_CLOSED`)
And the calling materialisation action aborts with a
typed error
And the runtime records an audit entry with
`operation=hook.timeout`, `result=denied`.

#### Scenario: cancellation propagates to the running hook

Given a `beforeRetrieval` hook is in progress
When the data plane cancels the calling retrieval
Then the runtime raises `HookCancelledError`
And the hook worker exits within the documented
cancellation grace window.

### Requirement: Hook failure policies match the documented §59.7 vocabulary

The Hook Runtime MUST honour the documented §59.7 failure
policies: `FAIL_OPEN`, `FAIL_CLOSED`, `WARN_ONLY`,
`DISABLE_PLUGIN`. `FAIL_OPEN` MUST allow the calling
data-plane action to continue and record a warning. `FAIL_CLOSED`
MUST abort the calling data-plane action with a typed error.
`WARN_ONLY` MUST record a warning and continue. `DISABLE_PLUGIN`
MUST transition the offending plugin to `failed` in the
`PluginRegistry` and record an audit entry. Security-sensitive
hooks (`beforeMaterialization`, `beforeMcpTool`,
`beforeAgentDelegation`) MUST fail closed by default;
observability-only hooks (`afterRetrieval`,
`afterContextAssembly`, `afterMcpTool`) MAY fail open by
default.

#### Scenario: WARN_ONLY records a warning and continues

Given an `afterRetrieval` hook with `failurePolicy="WARN_ONLY"`
When the hook raises a recoverable exception
Then the runtime records a warning
And the calling retrieval continues with the
documented result.

#### Scenario: DISABLE_PLUGIN transitions the plugin to failed

Given a `beforeRetrieval` hook with
`failurePolicy="DISABLE_PLUGIN"`
When the hook exceeds the bounded retry budget
Then the runtime transitions the plugin to `failed` in
the `PluginRegistry`
And the runtime records an audit entry with
`operation=hook.disable_plugin`, `result=allowed`
And subsequent retrievals do not dispatch that hook.

### Requirement: Hook Runtime emits a structured HookResult and an audit record

Every hook invocation MUST produce a structured `HookResult`
carrying `hookId`, `pluginId`, `event`, `durationMs`,
`status` (`ok`, `timeout`, `cancelled`, `error`),
`output` (structured dict, no raw secret values), and
`correlationId`. The runtime MUST record an audit entry for
every hook invocation through the Phase 7 `AuditLog`. The
audit entry MUST NOT contain the raw hook output; the audit
entry MUST contain the structured status and the
correlation id.

#### Scenario: hook result is structured and redacted

Given a `beforeMcpTool` hook returns a payload carrying a
raw `secret://` value
When the runtime records the audit entry
Then the audit entry does NOT contain the raw secret
value
And the audit entry contains the documented §59.13
fields.

### Requirement: Hook Runtime enforces the documented authorisation

Every hook invocation MUST consult the Phase 7 `PolicyEngine`
before dispatching the hook payload. The runtime MUST raise
the typed `DeniedError` when the policy engine returns
`DENY`. The runtime MUST raise the typed `ApprovalRequired`
when the policy engine returns `REQUIRE_APPROVAL`. Hooks that
request the `audit.write`, `secret.reference` or
`secret.resolve` capabilities MUST be authorised before they
can read or write the underlying state.

#### Scenario: hook with secret.resolve is denied for a read-only coding agent

Given a `beforeRetrieval` hook requests the
`secret.resolve` capability
and the calling agent has the documented read-only
coding-agent capability set from §59.8
When the runtime consults the policy engine
Then the policy engine returns `DENY`
And the runtime raises `DeniedError`
And the calling retrieval aborts with a typed error.

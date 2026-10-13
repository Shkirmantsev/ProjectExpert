# ui-extension Specification delta

## Purpose

Expose the UI Extension Registry with declarative UI descriptors and the no-arbitrary-JavaScript rule.

## Requirements


### Requirement: UI Extension registry accepts only declarative descriptors

The UI Extension registry MUST accept only declarative UI
descriptors. The supported descriptor shapes are:

```text
settingsPanel    — settings panel for the plugin
statusPanel      — status panel for the plugin
dashboardWidget  — dashboard widget for the plugin
menuItem         — menu item for the plugin
```

Every descriptor MUST declare a stable `id`, a `kind` from
the documented set, a `title`, an optional `description`,
an optional `icon` (declared by name only, never as inline
SVG or data URI), an optional `route` (declared by path
only, never as inline JavaScript), and the documented
configuration schema. The registry MUST reject any
descriptor that does not match the documented schema with
the typed `InvalidUiExtensionDescriptorError`.

#### Scenario: registry accepts a settingsPanel descriptor

Given a descriptor carries `kind="settingsPanel"`,
`title="Audit Export"`, `route="/plugins/audit-export"`
When the registry attempts to register the descriptor
Then the registry accepts the descriptor
And the registry records an audit entry with
`operation=ui_extension.register`, `result=allowed`.

#### Scenario: registry rejects an unknown kind

Given a descriptor carries `kind="rawHtml"`
When the registry attempts to register the descriptor
Then the registry raises `InvalidUiExtensionDescriptorError`
with `field="kind"`, `value="rawHtml"`.

### Requirement: UI Extension registry enforces the no-arbitrary-JavaScript rule

The UI Extension registry MUST reject any descriptor
carrying executable code. The forbidden field set includes:
`javascript`, `js`, `script`, `onclick`, `onerror`,
`onload`, `onmouseover`, `eval`, `Function`, `setTimeout`
(matching a string), `setInterval` (matching a string) and
any inline `<script>` block. The validator MUST walk every
string field recursively and reject any forbidden match. The
validator MUST reject any descriptor carrying a `data:`
URI in any field. The validator MUST reject any descriptor
carrying an inline `<script>` block in any field. The
validator MUST reject any descriptor carrying an inline
`<iframe>` block in any field.

#### Scenario: validator rejects a descriptor carrying onclick

Given a descriptor carries
`onclick="alert('xss')"` in the `title` field
When the registry attempts to register the descriptor
Then the registry raises
`InvalidUiExtensionDescriptorError` with
`field="title"`, `forbidden="onclick"`.

#### Scenario: validator rejects a descriptor carrying a data URI

Given a descriptor carries `icon="data:image/svg+xml;base64,..."`
When the registry attempts to register the descriptor
Then the registry raises
`InvalidUiExtensionDescriptorError` with
`field="icon"`, `forbidden="data_uri"`.

### Requirement: UI Extension registry records an audit entry on every registration

Every `register` / `unregister` call MUST record an audit
entry with `actorType`, `actorId`, `operation`, `resource`,
`policyDecision`, `result`, `duration` and `correlationId`.
The registry MUST consult the Phase 7 Policy Engine before
mutating registry state. A `register` request that requires
`mcp.admin` capability MUST return `REQUIRE_APPROVAL` for
non-administrator actors.

#### Scenario: register requires approval for a Developer

Given a `Developer` invokes `register` on a new UI
extension
When the registry consults the policy engine
Then the policy engine returns `REQUIRE_APPROVAL`
And the registry raises `ApprovalRequired`
And the registry state remains unchanged
And the registry records an audit entry with
`operation=ui_extension.register`,
`policyDecision="require_approval"`, `result=denied`.

### Requirement: UI Extension registry serialise is byte-stable

The UI Extension registry serialise MUST be byte-stable. Two
consecutive `serialise()` calls on the same registry
MUST return byte-identical JSON. The serialised form MUST
include every registered descriptor with its `id`, `kind`,
`title`, `description`, `icon` (name only) and `route`
(path only). The serialised form MUST NOT include any
forbidden field or any executable code.

#### Scenario: serialise is byte-stable

Given the registry has registered four descriptors
When the operator invokes `serialise()` twice
Then the two returned JSON strings are byte-identical.
And neither string contains a forbidden field or
executable code.

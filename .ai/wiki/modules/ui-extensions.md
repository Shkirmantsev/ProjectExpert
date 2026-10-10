---
id: modules.ui-extensions
title: Phase 7 UI Extension Registry module map
kind: module
status: active
summary: Phase 7 control-plane UI Extension Registry module map covering the declarative descriptor and the no-arbitrary-JavaScript rule.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-ui-extension/spec.md
  - pi_platform/core/control/ui_extensions.py
  - pi_platform/ports/control/ui_extensions.py
maintenance:
  mode: authored
related:
  - interfaces.ui-extension
---

# Phase 7 UI Extension Registry module map

The Phase 7 control plane ships the UI Extension Registry
that accepts only declarative UI descriptors and enforces the
no-arbitrary-JavaScript rule from §59.16.

## Declarative descriptor shapes

The documented §59.16 descriptor shapes:

```text
settingsPanel
statusPanel
dashboardWidget
menuItem
```

Every descriptor MUST declare a stable `id`, a `kind` from
the documented set, a `title`, an optional `description`,
an optional `icon` (declared by name only, never as inline
SVG or data URI), an optional `route` (declared by path
only, never as inline JavaScript), and the documented
configuration schema.

## No-arbitrary-JavaScript rule

The validator rejects any descriptor carrying executable
code. The forbidden field set includes `javascript`, `js`,
`script`, `onclick`, `onerror`, `onload`, `onmouseover`,
`eval`, `Function`, `setTimeout` and `setInterval`. The
forbidden pattern set includes `<script>`, `</script>`,
`<iframe>`, `</iframe>`, `javascript:`, `data:` and
`vbscript:` URIs.

The validator walks every string field recursively and
rejects any forbidden match. The validator rejects any
descriptor carrying a `data:` URI in any field.

## Wiring

The registry records an audit entry on every `register` /
`unregister` call through `attach_audit_log(audit_log)`.
The registry consults the Phase 7 `PolicyEnginePort`
before mutating registry state through
`attach_policy_engine(policy)`. A `register` request that
requires `mcp.admin` capability MUST return
`REQUIRE_APPROVAL` for non-administrator actors.

## Public surface

The public surface lives under
`pi_platform.core.control.ui_extensions.DefaultUiExtensionRegistry`.
The port is `pi_platform.ports.control.ui_extensions.UiExtensionRegistryPort`.
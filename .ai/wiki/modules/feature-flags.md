---
id: modules.feature-flags
title: Phase 7 Feature Flags module map
kind: module
status: active
summary: Phase 7 control-plane Feature Flags module map covering the §59.15 scope vocabulary and lifecycle states.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-feature-flags/spec.md
  - pi_platform/core/control/flags.py
  - pi_platform/ports/control/flags.py
maintenance:
  mode: authored
related:
  - interfaces.feature-flags
---

# Phase 7 Feature Flags module map

The Phase 7 control plane ships the Feature Flag registry
that resolves the documented §59.15 scope vocabulary and
the documented lifecycle states.

## Scope vocabulary

The documented §59.15 scope vocabulary:

```text
machine
project
branch
user
deploymentProfile
```

The registry resolves the most specific scope in the
documented order (`user > deploymentProfile > branch >
project > machine`). The `_SCOPE_ORDER` constant in
`ports/control/flags.py` carries the precedence list.

## Lifecycle states

The documented §59.15 lifecycle states:

```text
disabled
enabled
experimental
deprecated
```

An illegal transition raises the typed
`IllegalFeatureFlagTransitionError`. `experimental` flags
default to `disabled` unless the project explicitly enables
them.

## Git-versioned declarations and local overrides

Git-versioned feature declarations and local overrides
remain in separate sources. The registry records an audit
entry every time a local override shadows a
Git-versioned declaration.

## Adapters

The adapter layer ships three flag source adapters:

- `GitVersionedFlagSource` — loads flag declarations from
  the Git-versioned project configuration.
- `LocalOverrideFlagSource` — loads flag overrides from
  the local machine configuration.
- `MachineLocalFlagSource` — loads machine-scoped flag
  overrides from the local configuration.

The three adapters share the documented
`_EntryBackedFlagSource` private base.

## Public surface

The public surface lives under
`pi_platform.core.control.flags.DefaultFeatureFlagRegistry`.
The port is `pi_platform.ports.control.flags.FeatureFlagPort`.
---
id: interfaces.secret-provider
title: Phase 7 secret-provider interface
kind: interface
status: active
summary: Phase 7 §59 port surface for the secret-provider module.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-secret-provider/spec.md
  - pi_platform/ports/control/secret-provider.py
maintenance:
  mode: authored
related:
  - modules.secret-engine
---

# Phase 7 secret-provider interface

The port lives under `pi_platform.ports.control.secret-provider`
and the default production implementation lives under
`pi_platform.core.control.secret-provider`. See the linked
`modules.secret` node for the full module map.

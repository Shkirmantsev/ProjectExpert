---
id: interfaces.audit-log
title: Phase 7 audit-log interface
kind: interface
status: active
summary: Phase 7 §59 port surface for the audit-log module.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-audit-log/spec.md
  - pi_platform/ports/control/audit-log.py
maintenance:
  mode: authored
related:
  - modules.audit-engine
---

# Phase 7 audit-log interface

The port lives under `pi_platform.ports.control.audit-log`
and the default production implementation lives under
`pi_platform.core.control.audit-log`. See the linked
`modules.audit` node for the full module map.

---
id: adr.skill-ownership-boundary
title: Separate harness core and integration skill ownership
kind: adr
status: accepted
summary: Keep harness core synchronization separate from tool-generated top-level skills.
sourceRefs:
  - scripts/sync_skills.py
  - docs/SKILLS.md
maintenance:
  mode: authored
---

# Separate harness core and integration skill ownership

## Context

The harness keeps four small, directly discoverable core skills and routes its
larger catalog on demand. OpenSpec 1.12 uses the standard `.agents/skills/`
location for directly invokable Codex workflow skills. Scanning every top-level
skill as harness core conflates those ownership domains and lets one generator
overwrite another's output.

## Decision

The harness identifies its core through a fixed name list and synchronizes only
those skills. Integration-owned top-level skills may coexist in client discovery
directories, but their own tooling remains responsible for creation, refresh,
and removal. Catalog skills remain on-demand and are not copied as core.

## Consequences

- Codex can invoke OpenSpec workflows directly without weakening catalog
  routing for optional harness skills.
- Claude and OpenCode keep their client-specific OpenSpec-generated artifacts.
- Local and remote harness skill syncs remain bounded to four core skills.
- A missing named core skill fails synchronization explicitly.

## Alternatives rejected

- Classifying all top-level skills as core would expand synchronization and
  context exposure whenever an integration adds a skill.
- Moving OpenSpec skills into the catalog would break its standard direct
  invocation contract.
- Using the legacy `.codex/skills/` path would diverge from OpenSpec's current
  generator behavior.

## Verification

`tests.test_skill_runtime.SkillRouterTests` verifies both fixed core selection
and preservation of OpenSpec-owned Claude skills during local synchronization.
`tests.test_downstream_harness` additionally verifies both Claude/OpenCode
mirrors preserve integration and personal skills and detect mirror drift.

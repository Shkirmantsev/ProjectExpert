---
id: project.task-handoff
title: AI Task Handoff Lifecycle
kind: project
status: active
summary: Durable operational state that lets a new empty-dialog session continue active work safely.
sourceRefs:
  - AGENTS.md
  - scripts/session_state.py
  - schemas/session-state.schema.json
  - openspec/specs/2026-09-07-session-handoff/spec.md
maintenance:
  mode: hybrid
---

# AI Task Handoff Lifecycle

## Purpose and ownership

Conversation context is temporary. Active task state is project-visible and
survives a new AI dialog:

```text
agent lifecycle update
  -> scripts/session_state.py
  -> .ai/state/handoffs/<id>.json   canonical structured state
  -> .ai/state/CURRENT.md           generated concise view
  -> fresh session runs resume
  -> working-set hashes are checked before implementation continues
```

The handoff stores the objective, acceptance criteria, OpenSpec change, relevant
context, completed/remaining/blocked steps, decisions, file hashes, verification,
budgets, and next action. It never stores secrets, raw chats, hidden reasoning,
large logs, or copied source.

## Update moments

Agents start a checkpoint for every non-trivial task and update it after a
material implementation step, a decision, a blocker or repeated failure, and a
verification result. They also update it immediately before context compaction,
handoff, or their final response.

On session intake, agents read `CURRENT.md`. For a non-complete task they run:

```bash
python3 scripts/session_state.py resume
```

Exit code `3` reports changed or missing working files. Those files must be
re-inspected before continuing. Starting a second task cannot silently replace
an unfinished current task. `python3 scripts/session_state.py verify` checks that
the generated view exactly matches its canonical JSON, and `harness.py check`
runs that gate.

## Persistence boundary

Canonical JSON and generated Markdown are visible to Git. Uncommitted files are
available to new sessions in the same working tree; a different machine or clone
can see only committed and transferred state. Local locks and compatible legacy
checkpoints remain under ignored `tmp/local/`.

This operational state is not an alternative source for product requirements or
durable architecture. Agreed behavior stays in OpenSpec, implementation in code,
and reviewed explanatory knowledge in the Wiki.

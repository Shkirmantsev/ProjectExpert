# Session handoff

## Purpose

Define durable, non-secret task state so work can continue safely after an
interrupted or compacted agent session.

## Requirements

### Requirement: Durable active-task handoff

The harness SHALL persist non-secret operational task state in a project-visible
structured handoff and automatically regenerate a concise current-task view when
a task starts or advances.

#### Scenario: Resume from an empty dialog

- **GIVEN** a non-complete task has been started
- **WHEN** an agent begins a new session without the previous conversation
- **THEN** it can discover and validate the active task without knowing a session ID
- **AND** recover the goal, acceptance criteria, completed work, remaining work,
  decisions, verification state, working files, and next action

#### Scenario: Update a task

- **GIVEN** an active task exists
- **WHEN** the checkpoint command records a lifecycle update
- **THEN** the structured handoff and `.ai/state/CURRENT.md` describe the same
  updated state

#### Scenario: Legacy local checkpoint

- **GIVEN** a compatible checkpoint exists only under `tmp/local/sessions/`
- **WHEN** it is resumed or updated by ID
- **THEN** it remains readable
- **AND** it is promoted into the durable handoff store

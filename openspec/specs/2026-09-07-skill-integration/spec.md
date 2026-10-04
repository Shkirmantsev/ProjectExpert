# skill-integration Specification

## Purpose

Define how harness-owned core skills coexist safely with workflow skills that
external coding-tool integrations generate in the same discovery directories.

## Requirements

### Requirement: tool-owned skills coexist with harness core skills

The harness MUST distinguish its fixed directly discoverable core skills from
skills generated and owned by an integrated coding tool, even when both occupy
the top level of `.agents/skills/`.

#### Scenario: OpenSpec initializes Codex skills

Given the four harness core skills are installed
When OpenSpec initializes its Codex integration under `.agents/skills/`
Then all OpenSpec workflow skills remain directly discoverable
And the harness still identifies exactly its four named skills as harness core.

### Requirement: local skill sync preserves integration-owned outputs

Local skill synchronization MUST copy only harness-owned core skills to the
project-local Claude Code and OpenCode skill directories and MUST NOT delete or
overwrite tool-owned OpenSpec or unrelated personal skills. Codex MUST continue
using canonical `.agents/skills/` discovery without writes to global skill paths.

#### Scenario: sync after multi-client OpenSpec initialization

- **GIVEN** OpenSpec skills exist in canonical and client-specific directories
- **WHEN** local harness skill synchronization runs
- **THEN** the four harness core skills are refreshed in both project-local mirrors
- **AND** the OpenSpec-generated and personal skills remain present and tool-owned
- **AND** no user-global Codex directory is modified.

## ADDED Requirements

### Requirement: generated worktree pruning
Python and Go source discovery MUST prune generated .claude/worktrees paths before descending, while preserving authored .claude commands and ordinary worktrees documentation.

#### Scenario: nested generated checkout
- **WHEN** a source tree contains a nested .claude/worktrees checkout
- **THEN** neither inventory includes its duplicate files
- **AND** no filesystem files or Git worktree metadata are deleted

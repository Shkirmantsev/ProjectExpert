# Verification and quality gates

Every code-changing task requires explicit self-review before completion.

## Requirements

- Map changed behavior to the applicable request/OpenSpec requirement/scenario.
- Confirm non-goals, compatibility constraints and failure behavior.
- Report requirement/implementation contradictions explicitly.

## Diff/code review

Inspect the complete relevant diff for correctness, edge cases, architecture direction, project conventions, data/concurrency/retry effects, compatibility, generated-code boundaries, security, logging/observability, unrelated edits and debug/dead code.

## Evidence

- Run the smallest relevant checks first, then wider checks as needed.
- Record exact commands/results when useful for handoff/review.
- Update OpenSpec/Wiki/ADR artifacts affected by the change.

## Completion

Do not claim completion until relevant requirements were compared, the diff was reviewed, required checks passed or failures were reported accurately, and remaining assumptions/risks/unverified areas are visible.

---
name: openspec-change
description: Drive a non-trivial behavioral change with OpenSpec while keeping current specs, proposed deltas, implementation, and project Wiki temporally distinct.
---

# OpenSpec change

1. Start at `openspec/CURRENT.md`, then identify current behavior from `openspec/specs/`, implementation, and relevant Wiki pages.
2. Create/use one bounded change under `openspec/changes/<id>/`.
3. Produce proposal, behavioral specs, design, context-impact, and tasks in dependency order.
4. Requirements describe observable behavior; design contains implementation detail.
5. Mark proposed behavior as future until shipped/verified/archived.
6. Include focused tests and Wiki/ADR maintenance in tasks.
7. Run `python harness.py openspec-check`; run the installed OpenSpec CLI validator when available.
8. Report spec/implementation mismatches instead of hiding them.

## Project naming and adoption

Follow `openspec/README.md`: active changes are undated semantic kebab-case;
current capabilities use their first Git acceptance date as `YYYY-MM-DD-domain-capability`;
archives use their archive date without stacking prefixes. Match delta folders to
accepted dated capability IDs. When adopting or retiring requirements, update
`openspec/CURRENT.md` so each current spec appears exactly once; exclude proposals.
Keep historical archives unchanged. Run `python harness.py openspec-check` to
verify both the central view and naming before completion.

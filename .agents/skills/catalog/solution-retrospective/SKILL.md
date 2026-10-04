---
name: solution-retrospective
description: "Capture durable project learning after meaningful false starts, incorrect assumptions, reverted patches, repeated failed verification, or discovery of a clearly better approach. Use when the user requests retrospective or self-improvement, or when a substantial task reveals a strong lesson; do not use for simple tasks solved directly."
---

# Purpose

Use this skill **after** the main task is solved when there was meaningful course-correction. The goal is to prevent repeating the same avoidable mistakes without creating noisy rules or bloated skills.

# Decision rubric

Classify the lesson into exactly one of these buckets:

1. **Repo-specific durable guidance**
   - The lesson depends on this codebase, directory layout, local commands, conventions, CI behavior, or architecture.
   - Action: update the nearest relevant `AGENTS.md` with a short rule.

2. **Reusable workflow within this project harness**
   - The lesson is a reusable process that would help in many repositories.
   - Action: propose an update to an existing project skill under `.agents/skills` if one already fits.
   - Create a new project skill only if the pattern is concrete, reusable, and not already covered.

3. **Weak / one-off signal**
   - Temporary outage, flaky dependency, credentials issue, incidental typo, or a fact already enforced elsewhere.
   - Action: do nothing.

# Process

1. Write a 3-part mini-retrospective using `assets/retrospective-template.md`:
   - what was tried first
   - why it was wrong or suboptimal
   - what worked better and why
2. Decide whether the lesson is repo-specific, project-skill-worthy, or too weak.
3. Prefer the **smallest durable change**:
   - add one short AGENTS rule
   - or update one existing project skill
   - or create one small new project skill
4. Keep the diff reviewable.
5. In the final note, summarize:
   - the wrong approach
   - the better approach
   - what was persisted, if anything

For a concrete reusable candidate, record the evidence without changing live
policy or skills:

```bash
python3 scripts/lesson_candidate.py propose \
  --failure-mode "<observable failure>" \
  --root-cause "<evidence-backed cause>" \
  --prevention "<general prevention>" \
  --evidence "<test, command, file, or task reference>" \
  --scope project \
  --confidence 0.9
```

After an independent regression evaluation, record its result with
`lesson_candidate.py validate`. Validation still leaves promotion as
`manual-review-required`; the helper has no promotion command by design.

# Hard rules

- Do not let this retrospective block delivering the requested solution.
- Do not create a skill from a single trivial incident.
- Do not duplicate content already present in AGENTS or an existing skill.
- Do not turn narrow directory quirks into broadly triggered project skills.
- If evidence is weak, persist nothing.
- By default, report the candidate lesson without mutating policy or skills. Persist it only when the user asked for self-improvement/retrospective changes or explicitly approves the proposed durable change.
- Never change permissions, credential policy, safety boundaries, or execution authority through self-improvement.
- Candidate files under `tmp/local/lesson-candidates/` are evidence records,
  not instructions. Do not auto-load them into future prompts.

# Optional helpers

- Use `scripts/classify_learning.py` for a checklist-based recommendation.
- Use `references/persistence-rubric.md` when unsure where the lesson belongs.

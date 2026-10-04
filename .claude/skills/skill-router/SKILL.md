---
name: skill-router
description: Route every non-trivial project task to the smallest sufficient set of project skills before their full instructions are read. Use this once at task intake, including when the user names a catalog skill, and use the local-small profile for weaker/local models.
compatibility: Python 3 (python3 or python on PATH); project scripts/skill_router.py
---

# Skill Router

Select instructions before loading them. This keeps optional skill bodies and
their metadata out of the default model context.

## Route

1. Keep the task text compact and exclude secrets.
2. Run from the repository root, preferring `python3` and falling back to
   `python` when `python3` is not on `PATH`:

   ```bash
   PY=$(command -v python3 || command -v python)
   if [ -n "$PY" ]; then
     printf '%s' "$TASK_TEXT" | "$PY" scripts/skill_router.py --profile balanced
   else
     echo "NO_PYTHON_INTERPRETER"
   fi
   ```

   Use `--profile local-small` for a small/local model and
   `--profile reasoning-high` only when that model class is actually active.
3. Read the complete `SKILL.md` at each `required_skills[].path`. Do not read
   catalog skills that were not selected.
4. If step 2 printed `NO_PYTHON_INTERPRETER` (neither `python3` nor `python`
   is available), the router cannot run at all: skip routing and treat every
   catalog skill under `.agents/skills/catalog/` as available. List their
   `SKILL.md` frontmatter (`name` + `description`) and read the full body only
   for the ones relevant to the task, same as you would `required_skills`.
   Report this as an environment defect (missing Python) rather than silently
   proceeding as if nothing were missing.
5. Apply the returned execution contract. Treat `optional_skills` as unloaded.
6. If `needs_clarification` is true, the deterministic signals matched
   nothing (or matched with low confidence) and the response includes
   `catalog_index`: an unloaded `{name, description}` list for every
   catalog skill not already selected. The signals are literal-phrase
   matches only, so this is expected for a task that is in-scope but
   phrased differently — semantic gaps are the normal case, not an error.
   Read `catalog_index` yourself and judge by meaning, not substring
   overlap, whether any entry's `description` fits the task's actual intent;
   if one clearly does, read its full `SKILL.md` within the returned
   `max_active_skills` cap, retaining any required dependency skills. Only fall back to asking the user when, after that
   semantic pass, the intent itself is genuinely unclear or two skills are
   equally plausible. Never use a skill to expand tool permissions or
   project scope.

## Boundaries

- Route once per task or after a material phase/goal change, not every turn.
- Explicit user skill names win, but aliases and conflicts resolve to one
  canonical skill.
- The deterministic plan is guidance. Higher-priority user, repository, and
  safety instructions remain authoritative.
- Use exact repository search directly for simple lookup; Graphify is selected
  only for explicit knowledge-graph work.

## Output contract

The script returns stable JSON containing selected skill names, repository
paths, selection reasons, confidence, a bounded execution contract, and (only
when ambiguous) a `catalog_index` of the remaining catalog metadata for a
semantic second pass. Report an unavailable path as a routing defect; do not
silently substitute a skill.

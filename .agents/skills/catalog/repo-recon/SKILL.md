---
name: repo-recon
description: Build a compact deterministic repository profile before planning or delegation. Use on the first substantial task in a repository, after major structural changes, or when language/build/test/tooling assumptions are uncertain.
compatibility: Python 3 and Git when available; project scripts/repo_recon.py
---

# Repository Reconnaissance

Run from the active project root:

```bash
python3 scripts/repo_recon.py
```

Use the JSON profile to ground routing and planning in observed build files,
languages, instruction files, test roots, and declared command targets. The
profile is content-light and deterministic; it excludes ignored/generated,
temporary, dependency, and credential paths.

## Rules

- Read the nearest applicable `AGENTS.md` or equivalent instruction file before
  changes.
- Prefer repository wrappers and declared Make/package commands over guessed
  global commands.
- Treat a missing signal as unknown, not proof that a technology is absent.
- Re-run only when repository structure changes materially. Reuse the
  `profile_hash` within the same tree state.
- Use exact path/text search before symbol, AST, dependency-graph, or semantic
  expansion.

Do not turn reconnaissance into a whole-repository content dump. Return the
profile hash plus only the evidence needed by the next phase.

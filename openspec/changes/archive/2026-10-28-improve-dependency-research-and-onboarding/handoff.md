# Implementation handoff

Start here. This package is the requested instruction for another agent. **Planning is complete only when [verification](verification.md) says so. Product implementation remains pending in tasks.md.**

## Read only what you need

1. Read `AGENTS.md` and `.ai/state/CURRENT.md`.
2. Read [proposal](proposal.md) and [evidence](evidence.md).
3. Read [tasks](tasks.md), then the matching sections of [design](design.md) and corresponding delta under `specs/`.
4. For documentation work, read [README blueprint](readme-blueprint.md). For adoption, read [context-impact](context-impact.md).
5. Use `openspec/CURRENT.md` to retrieve accepted specs narrowly. Proposed deltas are not current behavior.

## Start or resume correctly

If CURRENT names an unfinished implementation session, run:

```bash
python3 scripts/session_state.py resume
```

Inspect drift before continuing. If the current planning session is complete, start implementation with:

```bash
python3 scripts/session_state.py start --id implement-dependency-research-and-onboarding --goal 'Implement the accepted dependency research and onboarding plan in verified slices' --acceptance 'All scenarios in improve-dependency-research-and-onboarding have explicit verification; help, real research, Wiki reuse and onboarding work end to end' --todo 'Execute tasks.md in order' --openspec-change improve-dependency-research-and-onboarding --context 'Read the change handoff, evidence and design; preserve unrelated working-tree changes'
```

Use the repository skill router for this new implementation phase. After each material step, use `session_state.py checkpoint` with `--done`, remaining `--todo`, relevant `--file`, `--verified` or `--pending-verification`, decisions and `--next-action`. Never edit CURRENT or canonical handoff JSON manually. Do not replace another unfinished task silently.

## Work sequence and boundaries

Execute tasks 1 → 2 → 3 → 4 → 5 → 6 → 7. Keep each slice reviewable and its acceptance evidence separate. Start with deployment regressions; they provide a small deliverable before the larger research service. Documentation can be drafted early but final capability claims depend on verified implementation.

Reuse the Python adapters already shipped. Do not broaden source discovery to recursively ingest environments or node_modules. Do not equate file discovery with semantic analysis, class signatures with method bodies, declared versions with installed versions, or protocol acknowledgement with research. The orphan diagnosis is a hypothesis until reproduced. Do not add blanket orphan cleanup.

No work on the user's trade-analyzer checkout, no publishing, no source-code execution from dependencies and no automatic environment installation is authorized by this plan. Dependency acquisition in the product must honor its explicit operation and policy. Optional tool selection is an implementation decision with evidence, not a reason to pretend universal decompilation exists.

At planning intake, unrelated untracked files included two previous session JSONs, two root handbook Markdown files and a Hermes patch. Preserve them. Recheck actual git status at implementation intake; do not assume the list is exhaustive or still current.

## Focused checks

Existing test modules to extend (use the project's supported test environment):

```bash
python3 -m pytest tests/test_portable_deployment.py tests/test_one_command_production_ux.py
python3 -m pytest tests/test_python_dependency_intelligence.py tests/test_repository_source_discovery.py
python3 -m pytest tests/test_mcp_server.py tests/test_mcp_context_factory.py tests/test_phase_10_a2a.py
python3 -m pytest tests/test_llm_wiki.py tests/test_production_capability_gate.py
python harness.py openspec-check
openspec validate improve-dependency-research-and-onboarding --strict
python harness.py check
```

On hosts without a `python` alias (including this planning host), use `python3 harness.py` for the same harness commands. Inspect each suite's collection and results. Add focused service/Node/artifact fixtures; these existing suites cannot prove new behavior by themselves. Test PowerShell with `scripts/test_deployment_launchers.ps1` on an available supported host. Run real exported-kit repeated startup and clean venv/container acceptance separately. No Docker/GPU/Windows availability means those checks are NOT RUN, not PASS.

## Evidence required before handoff

For each slice record changed files, scenario/test mapping, exact commands, pass/fail/skip counts, environment and unresolved limitations. Report image digest and readiness evidence for container acceptance. Show MCP and A2A graph/code artifacts for a real fixture; show a stored and subsequently searchable Wiki revision; show repeat-query cache/tool-call evidence. Record actual supported lock, bytecode and source-map formats.

## Completion boundary

The planning session can be complete while this OpenSpec change remains active and all implementation tasks remain unchecked. The implementing agent may mark a task complete only with its acceptance evidence. Archive/adopt only after the whole implementation is accepted; maintain existing capability dates, assign dates to new ones at acceptance, and update CURRENT. Preserve failure evidence and explicit next action if blocked.

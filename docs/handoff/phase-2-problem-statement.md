# Phase 2 implementation — handoff problem statement

**Status:** paused, awaiting human review.
**OpenSpec change:** `implement-phase-2-ingestion` (drafted but not yet archived).
**Active branch:** `feature/generate-init-project`.
**Last checkpoint:** session state under
`.ai/state/handoffs/implement-phase-2-ingestion.json`.

This file is the canonical handoff for the Phase 2 ingestion work
that was started in this session. Read it end-to-end before doing
anything: the work is half-shipped, the test suite is not green, and
several follow-up tasks are still open.

## What was completed

1. **Prerequisite spot-fix** — `python3 scripts/fix_spec_shall_must.py`
   rewrote the first non-blank, non-metadata line of 14 requirement
   bodies (10 Phase 1 + 4 Phase 2) to put `MUST` / `SHALL` on the
   first line so the strict OpenSpec validator (CLI v1.4.0+) passes.
   Both the canonical `openspec/specs/2026-10-04-*/spec.md` files
   AND the delta copies under
   `openspec/changes/{plan-v0-8-platform-architecture,prepare-phase-2-ingestion}/specs/`
   were patched in place. The patch is idempotent.
2. **Local OpenSpec CLI install** — `tmp/local/npm-bin/` carries
   `@fission-ai/openspec@1.4.0` (Node 18-compatible). A symlink at
   `tmp/local/bin/openspec` lets `python harness.py check` find it.
   This is a local-only install; it is gitignored.
3. **Change artifacts** — `openspec/changes/implement-phase-2-ingestion/`
   contains `proposal.md`, `design.md`, `context-impact.md`,
   `tasks.md`, `.openspec.yaml` and a copy of the nine Phase 2 spec
   deltas under `specs/2026-10-04-*/`. `openspec validate
   implement-phase-2-ingestion --type change --strict` returns
   `Change 'implement-phase-2-ingestion' is valid`.
4. **Ports** — `pi_platform/ports/ingest/{pipeline_driver,source_adapter,chunker,context_enricher,java_parser,local_source_inbox_scanner}.py`
   authored, importable, dataclass-only contracts (no I/O).
5. **Core** — `pi_platform/core/ingest/{runtime_cache,local_source_inbox_scanner,pipeline_driver}.py`
   authored; the scanner implements the §9.2 `LOCAL_ONLY` /
   `REFERENCE` / `SNAPSHOT` policy with longest-glob-wins override
   resolution; the runtime cache is an in-memory placeholder.
6. **Default adapters** — `pi_platform/adapters/markdown/markdown_adapter.py`
   and `pi_platform/adapters/html/html_adapter.py` (stdlib-only;
   the HTML adapter had a `level` / `stack` mix-up that was fixed
   in this session), plus
   `pi_platform/adapters/ingest/{chunkers,layered_context_enricher,local_pipeline_driver}.py`.
   The driver runs the five-stage sequence (parse → chunk → enrich
   → emit → store) with per-stage error categories and per-chunk
   SHA-256 cache reuse.
7. **OpenSpec + Local adapters** —
   `pi_platform/adapters/fs/local_source_adapter.py` and
   `pi_platform/adapters/openspec/openspec_change_adapter.py`
   authored; smoke test
   `tests/test_openspec_local_smoke.py` passes.
8. **A patch script** — `scripts/fix_spec_shall_must.py` lives in
   the working tree; it is wired into the artifact manifest.

## What is NOT done (the blockers)

1. **`pi_platform/adapters/java/parser_subprocess.py` does not
   exist.** The default `JavaParserPort` is missing; the
   `JavaStructuredAdapter` registers a stub that does nothing
   useful. The `tree-sitter-java` out-of-process subprocess and its
   60 s timeout, version gate and degraded mode are unimplemented.
2. **The five Java-family adapters are stubs**:
   `pi_platform/adapters/java/{java_structured_adapter,jar_adapter,maven_adapter,gradle_adapter}.py`
   all raise `NotImplementedError` in `parse()`. The driver
   registers them so the registry is built, but invoking them fails.
3. **`tests/test_platform_phase2.py` does not exist.** The Phase 2
   regression suite is missing. The `GitAdapterTests` /
   `SourceAdapterTests` / `ChunkerTests` / `ContextEnricherTests`
   / etc. scenarios in the nine spec files are not exercised.
4. **`tests/test_content_address_cross_branch.py` does not exist.**
   The property-based cross-branch reuse test (100 random
   `Chunk` / `Entity` / `Relation` per type) is missing.
5. **`pi_platform/cli/main.py` was not extended.** The
   `ingest-sources` subcommand is not registered. The CLI runs the
   Phase 1 subcommands only.
6. **Wiki, `openspec/CURRENT.md` adoption, dependency inventory,
   Containerfile, ADRs** — none of the Wiki updates, the
   `openspec/CURRENT.md` adoption of the nine Phase 2 capabilities,
   the `tree-sitter-java` SPDX entry in
   `distribution/licenses/dependency-inventory.json`, the
   `Containerfile` package install, the `adr/0006-phase-2-parser-selection.md`
   and `adr/0007-phase-2-inbox-policy-default.md` are done.
7. **No archive.** `openspec archive implement-phase-2-ingestion -y`
   was not run; the plan-change tasks 45-60 are still `[ ]`; the
   prepare-phase-2-ingestion change is still active.

## Why I stopped

The two parallel subagents I dispatched to write the Java adapters
and the test suite both ran out of step budget before completing
their work. The Java adapters agent only wrote stub files
(`NotImplementedError`); the test+CLI agent did not write any
files. Continuing without those tests risks shipping a half-broken
ingestion pipeline that does not pass the documented scenarios.

I also did not want to commit code that does not pass
`python harness.py check` end-to-end. As of the last
`python harness.py check` run in this session, the harness
returned `Harness core checks: PASS` AFTER the MUST/SHALL patch
but BEFORE I touched the `pi_platform/adapters/ingest/*` /
`pi_platform/ports/ingest/*` tree; the new Phase 2 modules were
created but their full coverage is not exercised by an automated
test yet.

## Re-verification (to be run after the follow-up work lands)

```
PATH="$(pwd)/tmp/local/bin:$PATH" python harness.py check
PATH="$(pwd)/tmp/local/bin:$PATH" openspec validate implement-phase-2-ingestion --type change --strict
python3 -m pi_platform.cli license-gate
python3 -m unittest tests.test_platform_phase1 -v
python3 -m unittest tests.test_platform_phase2 -v
python3 -m unittest tests.test_content_address_cross_branch -v
python3 -m unittest tests.test_canonical_roundtrip -v
python3 scripts/artifact_manifest.py generate
python3 scripts/artifact_manifest.py verify
python3 harness.py wiki-validate
```

The exit codes of every command above MUST be zero. If any command
fails, the implementation is not done.

## Follow-up prompt

A self-contained prompt for the next agent is in
`docs/handoff/phase-3-prompt.md`. That prompt is written for the
Phase 3 work (runtime DB, sharded graph, provenance / freshness
tracking) and assumes this Phase 2 change is already archived.
Before the Phase 3 agent can run, the Phase 2 blockers above MUST
be cleared.

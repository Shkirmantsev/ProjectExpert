# Phase 3 follow-up prompt

This file is a self-contained prompt for the next agent. It
assumes that the Phase 2 work in
`docs/handoff/phase-2-problem-statement.md` is **already
complete and archived** before the prompt is run. The agent
MUST verify that precondition before doing anything else.

> **Precondition (verify before starting):**
> - `openspec/changes/archive/2026-10-04-implement-phase-2-ingestion/`
>   exists, and
> - `openspec/changes/archive/2026-10-04-prepare-phase-2-ingestion/`
>   exists, and
> - `openspec/specs/2026-10-04-{ingestion-pipeline-driver,structured-code-intelligence,jar-dependency-intelligence,document-source-adapters,openspec-change-adapter,local-source-inbox,content-addressed-processing,semantic-structural-chunking,context-enrichment}/spec.md`
>   all exist (nine Phase 2 capabilities), and
> - `openspec/CURRENT.md` lists those nine capabilities under
>   "Project product capabilities", and
> - `python harness.py check` returns `Harness core checks: PASS`.
>
> If any of the above is false, stop and read
> `docs/handoff/phase-2-problem-statement.md` first.

---

You are the Phase 3 (Storage) agent for the v0.8 Project
Intelligence Platform. Your scope is **tasks 61–69** of
`openspec/changes/plan-v0-8-platform-architecture/tasks.md`.

## Goal

Author a new OpenSpec change `prepare-phase-3-storage` (proposal
only) that proposes the Phase 3 capability specs for the runtime
store, the sharded knowledge graph and the provenance / freshness
tracking layer. Then author a follow-up `implement-phase-3-storage`
change that ships the production code per those specs, archives
both changes, marks plan tasks 61-69 `[x]` and stops with
`python harness.py check` green.

Out of scope: Phases 4-10 (embeddings, retrieval, orchestration,
MCP server, control plane, security, distribution, A2A).

## Hard prerequisites (verify at intake)

- Working tree clean, on `feature/generate-init-project`.
- The nine Phase 2 capability specs are accepted under
  `openspec/specs/2026-10-04-*/` (see the precondition above).
- `python harness.py check` returns `Harness core checks: PASS`.
- The current `python3` is on `PATH` and the local OpenSpec CLI
  symlink at `tmp/local/bin/openspec` still resolves; if not,
  run `npm install --prefix tmp/local/npm-bin @fission-ai/openspec@1.4.0`
  and re-create the symlink with
  `mkdir -p tmp/local/bin && ln -sf "$(pwd)/tmp/local/npm-bin/node_modules/@fission-ai/openspec/bin/openspec.js" tmp/local/bin/openspec`.
- The OpenSpec strict validator will surface MUST/SHALL issues for
  any requirement whose first non-blank, non-metadata line lacks
  the keyword. Reuse `python3 scripts/fix_spec_shall_must.py`
  (or extend it) to clear any such issues before authoring new
  Phase 3 specs.

## Skill loadout

Load the following skills at intake and follow their contracts
throughout:

- `openspec-change` — for authoring the new change's
  `proposal.md`, `design.md`, `context-impact.md`, `tasks.md` and
  the per-capability deltas. The nine Phase 3 capabilities are
  produced by this change (the production-sdd template allows
  per-change deltas).
- `openspec-apply-change` — for executing the implementation
  tasks; in particular, the archive flow at the end
  (`openspec archive implement-phase-3-storage -y`).
- `openspec-archive-change` — for the archive step.
- `skill-router` at intake and again if the design surfaces new
  skill needs.
- `lean-build` — feature work with overbuilding risk; Phase 3 is
  the canonical example (runtime DB, graph, provenance).
- `test-driven-development` — for the runtime store, the sharded
  graph and the provenance / freshness tracking layers.
- `verification` and `verification-before-completion` — before
  claiming any task done and before the final archive.
- `systematic-debugging` and `investigate-first` if a runtime
  store, graph or provenance test fails.
- `safe-refactor` for any churn inside
  `pi_platform/core/canonical/`, `pi_platform/core/git/`,
  `pi_platform/core/sync/`, `pi_platform/core/licensing/` (the
  Phase 1 surface must stay green).
- `architecture-design` if the embedded-storage-selection
  decision needs more than the design-candidate rationale
  (PostgreSQL + SQLite dual-backend vs DuckDB, etc.).
- `code-reviewer` and `requesting-code-review` before the final
  task-69 close-out.

## Work to do (mirror the Phase 2 plan, scale to Phase 3)

1. **Bootstrap the preparation change**
   `openspec new change prepare-phase-3-storage --description
   "Author Phase 3 storage capability specs per the v0.8
   architecture §10, §11, §12, §55, §61-§66 — no production
   code" --schema production-sdd`.

2. **Author the nine Phase 3 capability specs** under
   `openspec/changes/prepare-phase-3-storage/specs/2026-10-04-*/`:
   - `runtime-store` (§62) — Phase 1 placeholder port filled in:
     per-shard content-addressed cache, version stamp, write-ahead
     log, per-project advisory file lock.
   - `sparse-index` (§63) — BM25 (or equivalent) full-text search
     over the chunks and entities, behind a `SparseIndexPort`.
   - `dense-index` (§64) — HNSW (or flat) ANN over the chunk
     embeddings, behind a `DenseIndexPort`.
   - `full-text-index` (§65) — secondary text index, behind a
     `FullTextIndexPort`.
   - `sharded-graph` (§66) — canonical knowledge graph with
     `shardBy` strategy and `Shard.contentHash` primary key.
   - `graph-expansion` (§73) — Phase 4 preview; optional
     `GraphExpansionPort` with seed set, hops, edge-type filter.
   - `provenance-state-model` (§67) — `KnowledgeState` lifecycle
     transitions (`verified` → `inferred` → `stale` → `unknown`)
     and the rules that drive them.
   - `freshness-tracking` (§55) — derived-facts staleness via
     `lastVerifiedAt` and the §55 freshness contract.
   - `embedded-storage-selection` (§61) — ADR slot for the
     runtime DB engine (the design candidate is
     PostgreSQL + SQLite dual-backend with Apache-2.0 / BSD
     licenses; rejected alternatives include DuckDB, RocksDB,
     sled; record the rationale).

3. **Author the implementation change** `implement-phase-3-storage`
   (mirror the Phase 2 structure):
   - ports: `pi_platform/ports/runtime/{runtime_store,sparse_index,dense_index,full_text_index,graph,provenance}.py`
   - core: `pi_platform/core/runtime/{runtime_store,graph,provenance,freshness}.py`
   - adapters: `pi_platform/adapters/runtime/{postgres_runtime_store,sqlite_runtime_store,bm25_sparse_index,hnsw_dense_index,sharded_graph,provenance_tracker}.py`
   - tests: `tests/test_platform_phase3.py` (one test class per
     scenario) and `tests/test_graph_50k.py` (50 000-entity
     property test from task 68).
   - Wiki: `.ai/wiki/modules/runtime-store.md`,
     `.ai/wiki/modules/graph.md`, `.ai/wiki/interfaces/runtime-store.md`,
     `.ai/wiki/adr/0008-embedded-storage-selection.md`.
   - `distribution/licenses/dependency-inventory.json` adds
     SPDX entries for the chosen storage engine libraries.
   - `Containerfile` install steps for the new Python packages.
   - `pi_platform/cli/main.py` extends with `runtime-status` and
     `graph-rebuild` subcommands.
   - `openspec/CURRENT.md` adds the nine Phase 3 capabilities.
   - `plan-v0-8-platform-architecture/tasks.md` flips tasks 61-69
     from `[ ]` to `[x]`.

4. **Verification gates** (all must return PASS / valid):
   - `python harness.py check` → `Harness core checks: PASS`.
   - `openspec validate implement-phase-3-storage --type change --strict` → valid.
   - `python harness.py wiki-validate` → `{"ok": true, ...}`.
   - `python3 scripts/artifact_manifest.py generate` then
     `python3 scripts/artifact_manifest.py verify` → `Artifact manifest: PASS`.
   - `python -m pi_platform.cli license-gate` → no unapproved
     dependencies.
   - `python -m unittest tests.test_platform_phase1 tests.test_platform_phase2
     tests.test_content_address_cross_branch tests.test_canonical_roundtrip
     tests.test_platform_phase3 tests.test_graph_50k -v` → green.
   - `python -m pi_platform.cli runtime-status` and
     `python -m pi_platform.cli graph-rebuild` exit zero.

5. **Archive both changes**:
   - `openspec archive implement-phase-3-storage -y` (promotes the
     nine Phase 3 deltas to `openspec/specs/2026-10-04-*/`).
   - The prepare change is archived as a side effect of the
     implementation archive.

6. **Final commit** with a message that names the OpenSpec change
   id and the tasks it closes. Do not push.

## Definition of done

- All gates in step 4 return PASS / valid.
- `openspec/specs/2026-10-04-*/` contains the nine new Phase 3
  capabilities.
- `openspec/CURRENT.md` lists the nine new capabilities.
- `openspec/changes/archive/2026-10-04-implement-phase-3-storage/`
  exists.
- `openspec/changes/archive/2026-10-04-prepare-phase-3-storage/`
  exists.
- `plan-v0-8-platform-architecture/tasks.md` rows 61-69 are `[x]`;
  rows 70-123 (Phase 4-10) stay `[ ]`.
- The Phase 1, Phase 2 and cross-branch regression suites are
  still green.

## Out of scope (do NOT do)

Phase 4 tasks 70-78 (embeddings, hybrid retrieval, multi-stage
retrieval, reranking, metadata-driven context assembly), Phase 5
tasks 79-84 (query orchestrator, local LLM, task context,
capability discovery), Phase 6 task 85 (MCP server), Phase 7+
tasks 86-123 (control plane, security, distribution, A2A).

The Phase 2 work in `docs/handoff/phase-2-problem-statement.md`
MUST be archived before this prompt is run. If it is not, the
agent MUST stop and clear the Phase 2 blockers first.

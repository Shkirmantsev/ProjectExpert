# Design — prepare-phase-4-retrieval

## Current state

The repository contains the v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)),
the Phase 1 foundation change archived at
[`openspec/changes/archive/2026-10-04-implement-phase-1-foundation/`](../../archive/2026-10-04-implement-phase-1-foundation/),
the Phase 2 ingestion subsystem archived at
[`openspec/changes/archive/2026-10-04-implement-phase-2-ingestion/`](../../archive/2026-10-04-implement-phase-2-ingestion/),
the Phase 3 storage subsystem archived at
[`openspec/changes/archive/2026-10-05-implement-phase-3-storage/`](../../archive/2026-10-05-implement-phase-3-storage/),
the active `plan-v0-8-platform-architecture` change that owns the
Phase 4-10 task ordering, and the 23 accepted Phase 1 + Phase 2 +
Phase 3 capability specs under `openspec/specs/2026-10-04-*/`:

Phase 1:

- `project-knowledge-repository-layout`
- `canonical-knowledge-schema`
- `git-version-aware-runtime`
- `bidirectional-canonical-runtime-sync`
- `license-governance`

Phase 2:

- `ingestion-pipeline-driver`
- `structured-code-intelligence`
- `jar-dependency-intelligence`
- `document-source-adapters`
- `openspec-change-adapter`
- `local-source-inbox`
- `content-addressed-processing`
- `semantic-structural-chunking`
- `context-enrichment`

Phase 3:

- `embedded-storage-selection`
- `runtime-store`
- `sparse-index`
- `dense-index`
- `full-text-index`
- `sharded-graph`
- `graph-expansion` (Phase 4 preview port)
- `provenance-state-model`
- `freshness-tracking`

The Phase 1 product source tree is in place at `pi_platform/` with
the `core/{canonical,git,sync,licensing}` subpackages, the
`ports/__init__.py` aggregate, the `adapters/{fs,git}` default
adapters, the `runtime/cache.py` Phase 1 placeholder runtime cache
(now backed by the Phase 3 `RuntimeStore` default adapter), the
`embedding/embedding_model.py` Phase 1 stub
(`EmbeddingModelPort` placeholder) and the `cli/` entry point
exposing `init-project`, `hydrate`, `materialise`, `license-gate`,
`okf-validate`, `version-identity`, `wal-recover`, `health`, the
Phase 2 `ingest-sources` subcommand and the Phase 3
`runtime-status`, `graph-rebuild` subcommands.

The Phase 2 production source tree is in place at `pi_platform/`
with the `core/ingest/` subpackage, the `ports/ingest/` aggregate
and the per-family `adapters/{fs,markdown,html,pdf,openapi,java,
openspec,ingest}/` adapters. The Phase 2 regression suite
(`tests/test_platform_phase2.py`,
`tests/test_content_address_cross_branch.py`) plus the Phase 1
round-trip invariant (`tests/test_canonical_roundtrip.py`) and the
Phase 3 regression suite (`tests/test_platform_phase3.py`,
`tests/test_graph_50k.py`) plus the full `python harness.py check`
gate are green.

The repository does NOT yet contain any Phase 4 production code
under `pi_platform/retrieval/`,
`pi_platform/ports/retrieval/`, `pi_platform/core/retrieval/`,
`pi_platform/adapters/retrieval/`,
`pi_platform/adapters/runtime/embedding_model/` or any related
Phase 4 module. The Phase 1 `pi_platform/embedding/embedding_model.py`
stub documents that Phase 4 replaces it. No embedding-model or
reranker library has been added to
`distribution/licenses/dependency-inventory.json` (the inventory
still holds only the optional `tree-sitter-java` MIT entry from
Phase 2 and the Phase 3 runtime libraries). The Phase 4 task list
(`tasks.md` rows 70-78) is still `[ ]` in the planning change.

## Proposed design

This change is a planning artifact: it ships no production code.
The design below describes the technical approach the future
`implement-phase-4-retrieval` change will implement, expressed as
module boundaries, port contracts, adapter composition, data flow,
dependency license gate, compatibility and risks. The design
records the embedding-model selection rationale, the hybrid
fusion strategy, the multi-stage pipeline composition, the
production graph-expansion adapter, the pluggable reranker, the
metadata filter projection, the context assembler contract and the
retrieval benchmark fixture so the implementation work has
unambiguous technical contracts.

### EmbeddingModelPort (§25, §5.4)

The `EmbeddingModel` lives in
`pi_platform/core/retrieval/embedding_model.py` (new) and exposes an
`EmbeddingModelPort` abstract class in
`pi_platform/ports/retrieval/embedding_model.py` (new). The default
adapters live in `pi_platform/adapters/retrieval/embedding_model/`
(new):

- `MultilingualSentenceTransformerEmbeddingModel` — default
  CPU-capable multilingual adapter. The design candidate is
  `paraphrase-multilingual-MiniLM-L12-v2` (or an equivalent
  sentence-transformers family model) on a CPU-only Python
  runtime (Apache-2.0 model + Apache-2.0 runtime);
- `HashingEmbeddingModel` — stdlib-only fallback adapter that
  produces deterministic hash-based vectors. The fallback is
  language-agnostic but loses semantic alignment; the
  `runtime-status` CLI reports it as `active_backend="hashing"`
  so the operator can recognise the fallback path.

The default selection is decided by
`project-context.yaml:embedding.backend` (`multilingual-st` by
default; `hashing` fallback when the optional dependency is
absent).

Requirements covered:

- multilingual coverage — DE / EN / UK at parity, RU opt-in;
- CPU-capable deployment — no GPU required, no GPU block at
  startup, optional GPU adapter MAY register when present;
- replaceable provider — backend swap through
  `project-context.yaml:embedding.backend`;
- commercially-usable license — model + runtime SPDX identifiers
  appear in `distribution/licenses/dependency-inventory.json` and
  pass `LicenseGate` before the adapter is registered;
- deterministic for fixed `model_version()` and fixed input text;
- integration with the Phase 3 `DenseIndexPort` and the Phase 3
  freshness tracker so a model-version change triggers
  re-embedding of affected chunks.

Dependency license (planned):

| Adapter | Dependency | License | LicenseGate action |
|---|---|---|---|
| `MultilingualSentenceTransformerEmbeddingModel` | `sentence-transformers` | Apache-2.0 | allow |
| `MultilingualSentenceTransformerEmbeddingModel` (model) | `paraphrase-multilingual-MiniLM-L12-v2` | Apache-2.0 | allow |
| `MultilingualSentenceTransformerEmbeddingModel` (alt model) | `intfloat/multilingual-e5-base` | MIT | allow |
| `MultilingualSentenceTransformerEmbeddingModel` (alt model) | `BAAI/bge-m3` | MIT | allow |
| `HashingEmbeddingModel` | stdlib only | n/a | allow |
| `GpuEmbeddingModel` (opt-in) | `torch` CPU-only wheels | BSD-3-Clause | allow |

Rejected alternatives (captured for the future ADR 0009
`embedding-model-selection`):

- `text-embedding-ada-002` — rejected for non-local execution
  (the §25 "local execution" requirement);
- non-multilingual BERT variants — rejected for failing the
  multilingual coverage requirement;
- non-Apache / non-MIT model licenses — rejected for failing
  the §5.4 model-license gate.

### HybridRetrieval port (§27, §28, §26, §33)

`HybridRetrievalPort` lives in
`pi_platform/ports/retrieval/hybrid_retrieval.py` (new). The
default composition adapter lives in
`pi_platform/core/retrieval/hybrid_retrieval.py` (new) and the
adapters live in `pi_platform/adapters/retrieval/`:

- `HybridRetrieval` — composition port that fuses dense ANN
  (Phase 3 `DenseIndexPort`), sparse BM25 (Phase 3
  `SparseIndexPort`) and exact-identifier lookup into a single
  ranked candidate set;
- `IdentifierQueryDetector` — utility that recognises engineering
  identifiers in a query string and routes them to exact lookup
  before vector search.

Fusion strategy:

- the design candidate is **reciprocal rank fusion (RRF)** with
  `dense_weight=0.5`, `sparse_weight=0.5` defaults;
- rejected alternatives: linear weighted sum (rejected for being
  score-distribution-sensitive across the dense and sparse
  indexes), learned fusion (rejected for requiring labelled
  training data that the platform does not ship by default).

The fusion strategy is configurable through
`project-context.yaml:retrieval.fusion.strategy`. The
`stats()` response reports the active strategy.

Identifier detection grammar:

- the design candidate is a regex-based identifier detector that
  matches `^[A-Z][A-Z0-9_.-]+$`, `[A-Za-z][A-Za-z0-9]*JpaMapper$`
  and `0x[0-9a-fA-F]+`;
- rejected alternatives: full AST-based detection (rejected for
  being too expensive at the query-time budget) and LLM-based
  detection (rejected for adding an unnecessary LLM call before
  the cheapest deterministic retrieval mechanism).

### MultiStageRetrieval orchestrator (§29, §33)

`MultiStageRetrievalPort` lives in
`pi_platform/ports/retrieval/multi_stage_retrieval.py` (new). The
default orchestrator lives in
`pi_platform/core/retrieval/multi_stage_retrieval.py` (new).

Pipeline stages and default budgets (token-equivalent):

| Stage | Default budget | Driver |
|---|---|---|
| 1. candidate generation | 50 candidates | `HybridRetrievalPort.query` + `exact_id` |
| 2. fusion | 50 candidates | `HybridRetrievalPort.query` |
| 3. metadata / version / security filter | 40 candidates | `MetadataFilterPort.apply` |
| 4. graph expansion | 30 entities | `GraphExpansionPort.expand` |
| 5. hierarchy expansion | 30 entities | `GraphExpansionPort.expand` (`edge_types=["PART_OF"]`) |
| 6. reranking | 20 candidates | `RerankerPort.rerank` (only when `enableReranking=True`) |
| 7. context assembly | `contextBudget` | `ContextAssemblerPort.assemble` |

The orchestrator reports every stage entry in the
`stageReports` list with `{"in": int, "out": int, "duration_ms":
int, "budget_exhausted": bool}`. The total consumed budget MUST NOT
exceed `contextBudget`. The pipeline MUST remain deterministic for
fixed inputs (within the documented numerical tolerance).

### Production GraphExpansion adapter (§31)

The production adapter lives in
`pi_platform/adapters/runtime/graph_expansion.py` (new) and
replaces the Phase 3 stub adapter at startup. The production
adapter walks the Phase 3 `GraphPort` and applies the documented
`hops`, `edge_types` and `budget` parameters.

The adapter MUST honour the §17 ANN-vs-knowledge-graph separation:
the production adapter MUST NOT consult the ANN graph; it MUST
ONLY walk the canonical `GraphPort`.

The hierarchy-expansion stage of the multi-stage pipeline reuses
the same adapter with `edge_types=["PART_OF"]` so the
parent-document, parent-section and parent-chunk relationships are
reachable without a second expansion implementation.

### RerankerPort (§30)

`RerankerPort` lives in
`pi_platform/ports/retrieval/reranker.py` (new). The default
adapters live in `pi_platform/adapters/retrieval/reranker/`
(new):

- `CrossEncoderReranker` — default cross-encoder reranker; the
  design candidate is `cross-encoder/ms-marco-MiniLM-L-6-v2` or
  an equivalent MIT-licensed cross-encoder on CPU;
- `Bm25LightReranker` — stdlib-only BM25-based reranker fallback;
- `ColBertStyleReranker` (optional) — ColBERT-style late
  interaction; activates only when
  `project-context.yaml:retrieval.reranker.family == "colbert"`
  AND the optional dependency is present.

The active reranker family is selected through
`project-context.yaml:retrieval.reranker.family`. The pipeline
falls back to the lighter-weight reranker when the
cross-encoder dependency is absent.

Dependency license (planned):

| Adapter | Dependency | License | LicenseGate action |
|---|---|---|---|
| `CrossEncoderReranker` | `sentence-transformers` (cross-encoder helpers) | Apache-2.0 | allow |
| `CrossEncoderReranker` (model) | `cross-encoder/ms-marco-MiniLM-L-6-v2` | MIT | allow |
| `Bm25LightReranker` | stdlib only | n/a | allow |
| `ColBertStyleReranker` (opt-in) | `colbert-ai` or `pylate` | MIT | allow (review) |

### MetadataFilter and MetadataFilterPort (§24, §23, §56)

`MetadataFilter` (value type) and `MetadataFilterPort` (filter
projection) live in
`pi_platform/ports/retrieval/metadata_filter.py` (new). The default
filter adapter lives in
`pi_platform/core/retrieval/metadata_filter.py` (new) and the
adapters live in `pi_platform/adapters/retrieval/`:

- `MetadataFilter` — value type carrying `queryDate`,
  `projectVersion`, `languages`, `businessDomains`, `modules`,
  `requirementIds`, `securityClassifications`;
- `MetadataFilterPort.apply(filter, hits)` — drop hits whose
  metadata violates the filter, with a documented drop reason.

Drop-reason priority (deterministic):

1. `temporal_invalid` (the §24 rule);
2. `version_mismatch`;
3. `security_denied` (the §56 enterprise boundary);
4. `language_mismatch`;
5. `domain_mismatch`;
6. `module_mismatch`;
7. `requirement_mismatch`;
8. `authoritative_preference` (only set by the context assembler
   when the budget is binding).

### ContextAssemblerPort (§32)

`ContextAssemblerPort` lives in
`pi_platform/ports/retrieval/context_assembler.py` (new). The
default assembler lives in
`pi_platform/core/retrieval/context_assembler.py` (new).

Bundle shape:

- `hits` — deduplicated, budget-bounded hit list;
- `dedupedEntities` — the deduplicated canonical chunk / entity /
  relation list;
- `citations` — per-hit citation with `chunkId`, `contentHash`,
  `sourceReference`, `projectVersion`, `evidenceWeight`;
- `authoritativeHits` — hits with `KnowledgeState == "verified"`;
- `conflictingHits` — pairs of hits that disagree on a documented
  fact;
- `uncertainHits` — hits whose `KnowledgeState` is `inferred`,
  `assumption`, `stale` or `unknown`;
- `budgetUsed` — total consumed token-equivalent budget;
- `droppedHits` — hits dropped with reason
  (`deduplicated`, `budget_exhausted`, `authoritative_preference`);
- `explanations` — human-readable explanations for conflicting
  pairs and uncertainty surfacing.

The bundle is the input the Phase 5 `TaskContextBuilder`
(`openspec/specs/2026-10-04-task-context-builder/`) consumes.

### Retrieval benchmark fixture (§49)

The benchmark fixture contract is documented in
[`specs/2026-10-04-retrieval-benchmark/spec.md`](specs/2026-10-04-retrieval-benchmark/spec.md).
The production implementation lives in
`tests/test_retrieval_benchmark.py` and ships with the future
`implement-phase-4-retrieval` change, not with this preparation
change.

The fixture contract covers:

- a fixed canonical corpus (≥ 1000 chunks, ≥ 100 entities);
- a labelled query set (≥ 100 queries with ground-truth hits);
- per-query metrics (recall, precision, MRR, latency, cache hit,
  branch hydration, stale detected, plugin setup ok);
- aggregate report (recall, precision, MRR, latency p50 / p95,
  cache hit rate, plugin setup success rate).

### Module layout (planned for the future implementation change)

The future `implement-phase-4-retrieval` change populates:

- `pi_platform/core/retrieval/` — new core subpackage for
  `HybridRetrieval`, `MultiStageRetrieval`, `EmbeddingModel`,
  `Reranker`, `MetadataFilter`, `ContextAssembler` implementations;
- `pi_platform/ports/retrieval/` — new ports subpackage for
  `EmbeddingModelPort`, `HybridRetrievalPort`,
  `MultiStageRetrievalPort`, `RerankerPort`, `MetadataFilterPort`,
  `MetadataFilter`, `ContextAssemblerPort`,
  `RetrievalQuery`, `RetrievalResult`, `RetrievalHit`,
  `ContextBundle`, `ContextBudget`;
- `pi_platform/adapters/retrieval/` — new default adapters
  (`MultilingualSentenceTransformerEmbeddingModel`,
  `HashingEmbeddingModel`, `HybridRetrieval`,
  `IdentifierQueryDetector`, `CrossEncoderReranker`,
  `Bm25LightReranker`, `ColBertStyleReranker`,
  `MetadataFilterAdapter`, `ContextAssemblerAdapter`);
- `pi_platform/adapters/runtime/graph_expansion.py` — new
  production adapter that replaces the Phase 3 stub adapter;
- `tests/test_retrieval_benchmark.py` — new Phase 4 evaluation
  fixture;
- `distribution/licenses/dependency-inventory.json` — new SPDX
  entries for the chosen embedding model, reranker and optional
  ColBERT-style runtime;
- `pi_platform/cli/main.py` — extends with `retrieval-status`,
  `embedding-status`, `reranker-status` subcommands.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Embedding-model licence liability | every adapter's `license_id()` is checked by `LicenseGate` before registration; rejected licenses MUST NOT register |
| Multilingual alignment drift | the default multilingual model ships with a documented alignment threshold that the runtime reports under `stats()` |
| Pipeline non-determinism | every port disables non-determinism through explicit configuration; the benchmark asserts determinism |
| Budget runaway | every stage reports `budget_exhausted` and stops; the pipeline totals MUST NOT exceed `contextBudget` |
| Conflict surfacing noise | the assembler documents a conflict-detection policy in the future `design.md`; only `KnowledgeState`-relevant conflicts are surfaced |
| Phase 3 round-trip regression | the Phase 1 `tests/test_canonical_roundtrip.py` and the Phase 2 / Phase 3 regression suites MUST continue to pass byte-for-byte |
| Hybrid fusion drift | the fusion strategy is configurable; the `retrieval-benchmark` records `precision_with_reranker` vs `precision_without_reranker` to surface drift |

## Compatibility / migration impact

This change is a pure planning artifact. It introduces no new
runtime code or dependency; it only authorises the future
implementation change. The Phase 1 / Phase 2 / Phase 3 regression
suites and the harness check MUST remain green throughout this
preparation change.

## OpenSpec CLI conventions

The change folder uses lowercase kebab-case without a date prefix
(`prepare-phase-4-retrieval`) per
[`openspec/config.yaml`](../../config.yaml). The eight spec
deltas are dated with the future acceptance date `2026-10-04`
matching the Phase 1 / Phase 2 / Phase 3 archive conventions. The
archive step for the future `implement-phase-4-retrieval` change
will produce `archive/2026-10-04-implement-phase-4-retrieval/` and
rename the delta folders to drop the date prefix in the
change-root view.

## Verification of this preparation change

- `python harness.py check` MUST pass;
- `openspec validate prepare-phase-4-retrieval --type change
  --strict` MUST return `valid`;
- `openspec validate --all --strict` MUST NOT regress on the
  Phase 1 / Phase 2 / Phase 3 deltas;
- `python harness.py wiki-validate` MUST remain `{"ok": true,
  ...}` because this preparation change does NOT edit the Wiki;
- `python3 scripts/artifact_manifest.py verify` MUST return
  `Artifact manifest: PASS`;
- the Phase 1 / Phase 2 / Phase 3 regression suites MUST remain
  green (no production code is added by this change).

## Out-of-scope design decisions

The following design decisions belong to later phases and are NOT
finalised by this change:

- Phase 5: query orchestrator, local LLM, task context and
  capability discovery — Phase 5 tasks 79-83;
- Phase 6: MCP server exposing the retrieval ports — Phase 6
  task 85;
- Phase 7: control plane, security, distribution, A2A — Phase 7+
  tasks 86-123;
- the Wiki materialisation of the retrieval modules — Phase 4
  task 78 ships with the future `implement-phase-4-retrieval`
  change, not with this preparation change.
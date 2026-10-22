# Proposal — production semantic search and branch reconciliation

Source of truth for this change:
`ProjectExpert-production-semantic-search-branch-reconciliation-plan.md`
(plan §1–§102). PR slices come from plan §79; ordering from plan §80;
external verified facts from plan §101; the closing architectural
principle from plan §102.

## Why

The v0.8 platform already carries the right architecture: Git-canonical
knowledge, ports/adapters, content addressing, runtime cache separation,
profile identity, hybrid retrieval and a Control Plane. The production
path, however, still resolves to production-shaped stubs:

- the EmbeddingGemma 2 binding raises "not bound in this build"
  (`pi_platform/adapters/retrieval/embeddinggemma2_embedding_model.py`);
- the Qwen3 embedding binding raises "not bound in this build"
  (`pi_platform/adapters/retrieval/qwen3_embedding_model.py`);
- the USearch dense backend reports `usearch-stub` and delegates to flat
  memory search (`pi_platform/adapters/runtime/usearch_dense_index.py`);
- the Docling PDF adapter synthesizes a vendor-shaped document instead of
  parsing one (`pi_platform/adapters/pdf/docling_pdf_adapter.py`);
- the multimodal figure binding is a stub behind the multimodal profile
  (`pi_platform/adapters/retrieval/figure_embedding_stub.py`);
- accepted profile records still carry `model_revision="pinned-stub"`
  (`pi_platform/ports/retrieval/embedding_profile.py`) and
  `distribution/licenses/model-licenses.json` lists six entries with
  revision/status `pinned-stub`;
- the default UI retrieval composition hashes the corpus at query time
  instead of querying the persistent semantic index, so UI and MCP do not
  share retrieval semantics (plan §27);
- `ReconcileService` accepts `previous_head` and `current_head`
  (`pi_platform/core/sync/reconcile.py`, `ReconcilePort` in
  `pi_platform/ports/__init__.py`) but performs a current-only manifest
  scan, so old-branch evidence can remain searchable after a branch
  switch (plan §31, §38).

Plan §2 makes "no silent production stubs" a non-negotiable requirement:
a component is either real-and-available, real-and-not-installed (with an
actionable error), or explicitly disabled — never "looks enabled but runs
a stub". Plan §99 states the user story that must work end to end with
one command and one model choice. None of that is deliverable while the
production path resolves to stubs, and the twelve workstreams must land
in a dependency order (plan §80) that keeps the platform shippable after
every slice.

## Goal

Adopt the OpenSpec change
`production-semantic-search-and-branch-reconciliation` that:

- turns plan §79 into **twelve bounded PR slices** (PR1 configuration
  truthfulness, PR2 embedding port query/document roles, PR3 EmbeddingGemma 2
  binding, PR4 Qwen3 embedding binding, PR5 semantic index service,
  PR6 real USearch backend, PR7 unified production retrieval composition,
  PR8 persisted snapshot reconciliation, PR9 incremental repository source
  discovery, PR10 real Docling adapter and hybrid chunker, PR11 one-command
  production UX, PR12 production capability and release gates), ordered by
  the plan §80 dependency graph `PR1 → PR2 → PR3 → PR4 → PR5 → PR6 → PR7 →
  PR8 → PR9 → PR10 → PR11 → PR12` with the documented shortcut that PR10
  depends on PR2 only and may run beside PR3–PR9;
- defines **twelve additive behavioural capabilities** (delta folders under
  `specs/`, dated `2026-10-18` for first Git acceptance) whose requirements
  are observable behaviour only;
- identifies the accepted capabilities in `openspec/CURRENT.md` that these
  slices affect (embedding model, dense index, bidirectional canonical
  runtime sync, embedding execution profile, human interface web UI,
  one-click distribution, capability discovery, document source adapters,
  semantic structural chunking, license governance, integration quality
  gates) and classifies each impact as additive, modified or retired;
- records the external technical facts the design depends on — plan §101
  verified upstream capabilities and URLs for EmbeddingGemma 2
  (`https://huggingface.co/google/embeddinggemma-2`, Apache-2.0, 768d
  native with MRL 512/256/128, 8,192 context, task-specific query/document
  prompting, float32/bfloat16 recommended), Qwen3-Embedding-0.6B
  (`https://huggingface.co/Qwen/Qwen3-Embedding-0.6B`, Apache-2.0, 0.6B
  parameters, 32K context, up to 1024d with MRL, instruction-aware query
  embedding), USearch (`https://github.com/unum-cloud/USearch`, real native
  index with cosine metric, add/search, save/load/view) and Docling
  (`https://docling-project.github.io/docling/`, `DocumentConverter`,
  `DoclingDocument`, `HybridChunker`, Hugging Face tokenizer integration,
  MIT code license with separately inventoried model assets) — and requires
  re-verification of these facts at dependency upgrade time;
- adopts plan §102 as the closing architectural principle: source →
  canonical knowledge → runtime semantic state → one selected model →
  persistent vectors → real ANN → hybrid retrieval → context assembly →
  consumers, with the guarantees "no production stubs, no silent hashing
  fallback, no cross-model vector mixing, no stale previous-branch
  evidence, no model-switch Git churn, no requirement for users to
  understand internal index mechanics, one model choice → one command →
  working semantic ProjectExpert";
- produces a technical design that extends
  `pi_platform/{core,ports,adapters}/` without a new abstraction layer
  (plan §98) and a task list that an executor can run top to bottom with
  focused verification per PR.

Out of scope for this change:

- any source-code, container, Makefile or distribution edit — this change
  authors planning artifacts only;
- downloading model weights or pinning concrete revision hashes (the
  slices require immutable revisions to replace `pinned-stub`, but the
  literal hashes are chosen at binding time);
- redesigning ports/adapters, the control plane, MCP, the enterprise
  security boundary, `RuntimeCache`, `SqliteVectorRecordStore`,
  `EmbeddingProfile` identity, hybrid retrieval or the Context Assembler
  (plan §98);
- retiring the hashing embedding backend: it stays, restricted to the
  minimal/development profiles, unit tests and deterministic CI.

## Affected capabilities

### New capabilities (delta folders created in this change)

All twelve are **ADDITIVE**. Folder names carry the intended first
acceptance date `2026-10-18` and become the accepted identities
`openspec/specs/2026-10-18-<name>/` on adoption.

| Delta capability folder | PR | Plan reference |
| --- | --- | --- |
| `2026-10-18-production-runtime-configuration-resolver` | PR1 | §2, §19, §20, §61, §63 |
| `2026-10-18-embedding-port-query-document-roles` | PR2 | §7, §8, §11 |
| `2026-10-18-real-embeddinggemma2-binding` | PR3 | §6.1, §9, §12–§14 |
| `2026-10-18-real-qwen3-embedding-binding` | PR4 | §6.2, §10, §12–§14 |
| `2026-10-18-semantic-index-service` | PR5 | §24–§26 |
| `2026-10-18-real-usearch-dense-backend` | PR6 | §21–§23, §29, §30, §42 |
| `2026-10-18-unified-production-retrieval-composition` | PR7 | §27, §28 |
| `2026-10-18-persisted-runtime-snapshot-reconciliation` | PR8 | §31–§42 |
| `2026-10-18-repository-source-discovery-incremental` | PR9 | §43, §44 |
| `2026-10-18-real-docling-pdf-adapter-and-hybrid-chunker` | PR10 | §45–§50 |
| `2026-10-18-one-command-production-ux` | PR11 | §15–§18, §55–§60, §83–§88 |
| `2026-10-18-production-capability-and-release-gates` | PR12 | §64–§74, §89–§92, §97 |

### Accepted capabilities affected (per `openspec/CURRENT.md`)

| Accepted capability | Impact | Intent |
| --- | --- | --- |
| Embedding model (`2026-10-04-embedding-model`) | Modified | The accepted text-only embedding contract is extended to role-aware query/document requests (plan §7); the hashing backend is demoted to minimal/development only. Modified delta: `specs/2026-10-04-embedding-model/` is the existing delta and stays; the role-aware extension lives in the additive `2026-10-18-embedding-port-query-document-roles` delta. |
| Dense index (`2026-10-04-dense-index`) | Modified | A real native ANN backend with numeric key mapping, generation identity and atomic activation is added behind the accepted port (plan §21–§23, §29, §42); the flat backend remains for tests. Modified delta: `specs/2026-10-04-dense-index/` is the existing delta; the production-binding update lives in the additive `2026-10-18-real-usearch-dense-backend` delta. |
| Multi-stage retrieval (`2026-10-04-multi-stage-retrieval`) | Modified | Production stage order moves graph and hierarchy expansion to after rerank and selection so the reranker budget is spent only on direct candidates. Modified delta: `specs/2026-10-04-multi-stage-retrieval/spec.md` in this change supersedes the seven-stage order. |
| Hybrid retrieval (`2026-10-04-hybrid-retrieval`) | Modified | The legacy hash-scan dense fallback is removed from the production path; the dense channel is sourced from the persistent semantic index. Modified delta: `specs/2026-10-04-hybrid-retrieval/spec.md` in this change. |
| Runtime store (`2026-10-04-runtime-store`) | Modified | New `dense_keys` table, `source_generation` identifier, persisted active runtime snapshot, and tombstones for removed chunks. Modified delta: `specs/2026-10-04-runtime-store/spec.md` in this change. |
| MCP server (`2026-10-07-mcp-server`) | Modified | Retrieval tools fail closed during refresh; they share the unified production composition; model switch is administrator-only. Modified delta: `specs/2026-10-07-mcp-server/spec.md` in this change. |
| Bidirectional canonical runtime sync (`2026-10-04-bidirectional-canonical-runtime-sync`) | Modified | Incremental branch-switch reconciliation is strengthened to a persisted previous-served-snapshot diff with tombstones, working-tree fingerprints and a background version monitor (plan §31–§42). Behaviour lives in the additive `2026-10-18-persisted-runtime-snapshot-reconciliation` delta. |
| Embedding execution profile (`2026-10-16-embedding-execution-profile`) | Modified | Profile descriptors move from `pinned-stub` revisions to immutable real revisions; the user-facing startup modes become `production` / `minimal` / `development` (plan §63). Behaviour lives in the additive `2026-10-18-production-runtime-configuration-resolver` delta; the excluded profile set is documented in `excluded-profiles.md`. |
| Capability discovery (`2026-10-05-capability-discovery`) | Modified | Capability reporting must be truthful about real-vs-stub state (plan §61, §62). Behaviour lives in the additive `2026-10-18-production-runtime-configuration-resolver` and `2026-10-18-production-capability-and-release-gates` deltas. |
| Human interface web UI (`2026-10-11-human-interface-web-ui`) | Modified | First-start wizard, bootstrap progress surface, runtime settings and admin retrieval settings are added; existing UI contracts are not replaced. Behaviour lives in the additive `2026-10-18-one-command-production-ux` delta. |
| One-click distribution (`2026-10-11-one-click-distribution`) | Modified | Product Makefile targets, production image profile, persistent model volume and offline model-cache workflow (plan §5, §51–§58, §73). Behaviour lives in the additive `2026-10-18-one-command-production-ux` delta. |
| Document source adapters (`2026-10-04-document-source-adapters`) | Modified | Real Docling conversion replaces the synthetic adapter for the PDF family (plan §45–§48). Behaviour lives in the additive `2026-10-18-real-docling-pdf-adapter-and-hybrid-chunker` delta. |
| Semantic structural chunking (`2026-10-04-semantic-structural-chunking`) | Modified | Real hybrid chunking with tokenizer alignment to the active embedding model; canonical chunking stays model-independent (plan §48–§50). Behaviour lives in the additive `2026-10-18-real-docling-pdf-adapter-and-hybrid-chunker` delta. |
| License governance (`2026-10-04-license-governance`) | Modified | Real immutable model revisions, model-licence inventory truth and SBOM verification at release (plan §53, §54, §64). Behaviour lives in the additive `2026-10-18-production-capability-and-release-gates` delta. |
| Integration quality gates (`2026-10-12-integration-quality-gates`) | Modified | Real-model, real-ANN, real-Docling, branch-switch and end-to-end release gates (plan §64–§72, §89, §90). Behaviour lives in the additive `2026-10-18-production-capability-and-release-gates` delta. |
| Context enrichment, ingestion pipeline driver, resumable document ingestion | Additive | Existing contracts reused unchanged; only adapter wiring changes. |

**Retired capabilities: none.** The hashing embedding backend and the
flat dense backend remain accepted behaviour for the explicitly selected
`minimal` profile and deterministic CI.

## Compatibility / migration impact

This change is **additive at the artifact level** (new capability deltas)
and **behaviour-modifying at the production path level** (stubs leave the
production path). Migration rules:

1. **Audited-baseline discrepancy.** The plan names audited baseline
   commit `bc9be6e4ef481ee7a2a7827d165b6762f0aea66f`; that object does not
   exist in this clone (verified with `git cat-file -t`, 2026-10-19). No
   fetch was attempted. Implementation slices must therefore verify the
   plan's "verified current state" claims (plan §3) against the working
   tree at execution time instead of against that commit.
2. **Canonical Git knowledge is untouched.** Model switching
   (`gemma → qwen`) is a runtime retrieval configuration change: it
   reuses source/chunk knowledge, builds or reuses the selected vector
   namespace and ANN generation, and atomically activates it. It MUST NOT
   rewrite the project's durable Wiki or canonical knowledge (plan §2.4,
   §49).
3. **Vector namespaces stay isolated.** Every vector and ANN index belongs
   to exactly one embedding profile identity. Vectors from different
   model families, dimensions, normalization modes or revisions MUST NOT
   share a namespace; incompatible data is rejected with a redacted error,
   never silently mixed (plan §2.5).
4. **Runtime state remains disposable and untracked.** Vector records,
   ANN index generations, runtime snapshots, local settings and model
   caches stay under `.project-intelligence-cache/` (plus the configurable
   model cache volume) and are never committed (plan §2.3).
5. **Existing runtime data keeps working.** Stored vector records are
   reused when the retrieval text hash and profile identity match;
   anything profile-incompatible is rebuilt from stored vectors without
   re-embedding where possible, and re-embedded only for genuine misses
   (plan §24, §25).
6. **Startup profile migration.** The user-facing mode set becomes the
   three public modes `production`, `minimal`, `development` (plan §63).
   `minimal` is never selected silently; hashing is allowed only there
   and in tests. Existing developer workflows that relied on implicit
   hashing fallback must select `minimal` explicitly.
7. **Stub eradication is release-blocking.** `pinned-stub` /
   `not bound` / `usearch-stub` / synthetic Docling markers must not
   survive in production-reachable code paths; the PR12 gate enforces
   this (plan §64, §97).
8. **CLI/UI additions only.** `start`, `models`, Makefile product targets
   and admin retrieval settings are added; existing commands and API
   surfaces keep their contracts (plan §15–§18, §62).

### Reconciliation notes where the plan supersedes accepted specs

Per project policy the plan is preferred and the disagreement is
recorded here rather than silently rewritten:

- **Embedding model (`2026-10-04-embedding-model`).** The accepted
  contract describes a text-only embedding surface; plan §7 replaces it
  with an explicit query/document role contract. The role-aware contract
  supersedes the text-only shape for production callers; the hashing
  adapter continues to honour the accepted determinism requirements in
  minimal/test profiles.
- **Embedding execution profile (`2026-10-16-embedding-execution-profile`).**
  The accepted deployment preset list (`minimal / semantic-cpu /
  semantic-gpu / quality / contextualized / multimodal`) is superseded for
  user-facing startup by plan §63's three public modes. Internal execution
  presets (device policy, float policy) may survive as configuration
  details beneath `production`.
- **Human interface web UI (`2026-10-11-human-interface-web-ui`) and
  one-click distribution (`2026-10-11-one-click-distribution`).** PR11
  extends these capabilities additively (wizard, bootstrap progress,
  retrieval settings, product targets). It does **not** replace their
  accepted requirements: loopback binding, bearer auth, policy
  authorization, single-container default and launcher readiness
  semantics all remain in force.
- **Bidirectional canonical runtime sync
  (`2026-10-04-bidirectional-canonical-runtime-sync`).** The accepted
  "incremental branch-switch reconciliation" requirement is retained but
  its observable contract is strengthened by plan §31–§42: comparison is
  previous-served-snapshot vs current-snapshot, removals are tombstoned,
  and HEAD-identical working-tree changes trigger refresh.

## Related knowledge

Existing knowledge this change builds on:

- `kb://architecture/platform-overview`
- `kb://architecture/system-overview`
- `kb://modules/embeddings`
- `kb://modules/retrieval`
- `kb://modules/ingest`
- `kb://modules/runtime-store`
- `kb://modules/mcp-server`
- `kb://adr/0004-ports-and-adapters-extension-style`
- `kb://adr/0008-embedded-storage-selection`
- `kb://adr/0009-embedding-model-selection`
- `kb://adr/0010-hybrid-fusion-strategy`
- `kb://invariants/v0.8`

Knowledge to create or update during the slices
(full list in `context-impact.md`):

- `kb://production.semantic-binding`
- `kb://production.runtime-configuration`
- `kb://production.embedding-roles`
- `kb://production.semantic-index`
- `kb://production.usearch-generations`
- `kb://production.retrieval-composition`
- `kb://production.branch-reconciliation`
- `kb://production.source-discovery`
- `kb://production.docling-pipeline`
- `kb://production.one-command-ux`
- `kb://production.release-gates`

External facts relied on (plan §101, to be re-verified at upgrade time):

- `https://huggingface.co/google/embeddinggemma-2`
- `https://huggingface.co/Qwen/Qwen3-Embedding-0.6B`
- `https://github.com/unum-cloud/USearch`
- `https://docling-project.github.io/docling/`

Closing principle adopted from plan §102: no production stubs, no silent
hashing fallback, no cross-model vector mixing, no stale previous-branch
evidence, no model-switch Git churn, no requirement for users to
understand internal index mechanics; one model choice → one command →
working semantic ProjectExpert.

This proposal is the gate. Per-slice behaviour lives under `specs/`,
technical shape in `design.md`, knowledge impact in `context-impact.md`,
and the executable, dependency-ordered checklist in `tasks.md`.
---
id: interfaces.reranker
title: RerankerPort contract
kind: interfaces
status: active
summary: Phase 4 §30 pluggable reranker port — cross-encoder default, BM25-light fallback, optional ColBERT-style adapter.
sourceRefs:
  - pi_platform/ports/retrieval/reranker.py
  - pi_platform/core/retrieval/reranker.py
  - pi_platform/adapters/retrieval/bm25_light_reranker.py
  - pi_platform/adapters/retrieval/cross_encoder_reranker.py
  - pi_platform/adapters/retrieval/colbert_style_reranker.py
  - openspec/specs/2026-10-04-reranker-port/spec.md
maintenance:
  mode: authored
related:
  - interfaces.hybrid-retrieval
  - modules.retrieval
---

# RerankerPort contract

The §30 reranker port exposes a pluggable reranking surface that
the multi-stage retrieval pipeline (§29) invokes on the bounded
candidate set produced by the candidate generation, fusion,
metadata filter and graph / hierarchy expansion stages. Rerankers
operate on bounded candidate sets only; the multi-stage pipeline
MUST enforce a `rerankBudget` cap so a runaway candidate set
never reaches the reranker.

## Surface

- `rerank(query, candidates, *, top_k=10) -> Sequence[RetrievalHit]`
  — return the same `RetrievalHit` records reordered and
  truncated so the top `top_k` hits are the highest-scoring
  per the reranker.
- `score(query, candidate) -> float` — return a finite
  reranker score for a single candidate.
- `model_version() -> str` — return the opaque reranker-
  version string the platform records for capability discovery.
- `license_id() -> str` — return the SPDX identifier of the
  reranker model and runtime (see §5.4 model-license inventory).
- `family() -> str` — return the reranker family
  (`"cross-encoder"`, `"bm25-light"`, `"colbert-style"`).
- `stats() -> Mapping[str, int]` — operational counters
  including `calls`, `errors` and `budget`.

The `DEFAULT_RERANK_BUDGET` (50) cap is the default per-call
candidate budget; the multi-stage pipeline pre-trims its
candidate set to this budget before calling
`RerankerPort.rerank`.

## Reranker families

- `cross-encoder` — `CrossEncoderRerankerAdapter` (opt-in via
  the `sentence-transformers` extra). Wraps
  `cross-encoder/ms-marco-MiniLM-L-6-v2` (MIT). The default
  cross-encoder family per the §30 spec.
- `bm25-light` — `Bm25LightRerankerAdapter` (stdlib-only
  fallback, Apache-2.0). Always available. Default adapter
  registered when the `sentence-transformers` extra is absent.
- `colbert-style` — `ColBertStyleRerankerAdapter` (opt-in via
  the `colbert-ai` extra, MIT). The ColBERT-style late-
  interaction adapter per the §30 "pluggable reranker
  families" scenario.

The active family is selected through
`project-context.yaml:retrieval.reranker.family`; the platform
falls back to `bm25-light` when the requested family's
dependency is missing. The fallback path satisfies the §30
"lighter-weight reranker fallback" scenario.

## Determinism

The reranker stage is opt-in via
`RetrievalQuery.enableReranking=True`. When disabled, the
multi-stage pipeline MUST NOT allocate a reranker instance and
the `stageReports` MUST NOT list a `rerank` entry. The pipeline
bypasses the rerank stage entirely; this satisfies the §30
"reranker does not run when disabled" scenario.

## License gate

The `RerankerPort` adapter MUST use a reranker model and
runtime whose license satisfies the §5.1 preferred license
policy OR the §5.5 `LicenseGate` approval process for review-
required licenses. The model and runtime license SPDX
identifiers MUST appear in
`distribution/licenses/dependency-inventory.json` before the
adapter is registered. The license inventory records the
`cross-encoder-ms-marco-MiniLM-L-6-v2` model weights (MIT),
the `paraphrase-multilingual-MiniLM-L12-v2` model weights
(Apache-2.0) and the `sentence-transformers` Python package
(Apache-2.0).

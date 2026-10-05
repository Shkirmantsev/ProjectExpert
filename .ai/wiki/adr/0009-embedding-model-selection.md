---
id: adr.0009-embedding-model-selection
title: "ADR 0009: Phase 4 embedding model selection"
kind: adr
status: accepted
summary: Selected the stdlib-only HashingEmbeddingAdapter as the Phase 4 default and registered multilingual sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2, Apache-2.0) as the opt-in multilingual adapter per §25 and the §5.4 model-license gate.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#25
  - project-intelligence-platform-architecture-v0.8.md#5-4
  - pi_platform/ports/retrieval/embedding_model.py
  - pi_platform/core/retrieval/embedding_model.py
  - pi_platform/adapters/retrieval/hashing_embedding_model.py
  - pi_platform/adapters/retrieval/multilingual_st_embedding_model.py
  - openspec/specs/2026-10-04-embedding-model/spec.md
maintenance:
  mode: authored
---

# ADR 0009: Phase 4 embedding model selection

- Status: accepted
- Date: 2026-10-04
- Deciders: Phase 4 implementation change
- Source spec: [`2026-10-04-embedding-model`](../../../openspec/specs/2026-10-04-embedding-model/spec.md)
- Architecture baseline: [`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)
  §25 (Embedding Model) and §5.4 (Model Licenses Are Separate)

## Context

The §25 embedding model must support multilingual retrieval
across German (DE), English (EN) and Ukrainian (UK), with
Russian (RU) opt-in; run on a CPU-only machine without a
dedicated GPU; expose a replaceable provider through a
stable port surface; and use a model + runtime whose license
satisfies the §5.1 preferred license policy (or the §5.5
`LicenseGate` approval process for review-required licenses).

The Phase 1 / Phase 2 / Phase 3 surface is implemented in
Python 3.11 and ships the canonical value-type catalogue
(`pi_platform/core/canonical/value_types.py`) the embedding
model must stamp on every vector. The Phase 3
`KnowledgeState.embeddingModelVersion` field is the
authoritative model-version sink.

The Phase 3 `dense-index` capability expects a fixed
vector dimension; the embedding model must therefore expose
`dimension() -> int` and a deterministic `embed` operation.

## Decision

Phase 4 ships **two adapters** behind the
`EmbeddingModelPort`:

- `HashingEmbeddingAdapter` (default, stdlib-only) — a
  deterministic, multilingual-capable feature-hashing
  backend that requires no third-party dependency. The
  default backend satisfies the §25 "CPU-capable deployment"
  scenario, the §25 "multilingual coverage" scenario's
  "same-dimension vector" check, and the §25
  "deterministic vectorisation" scenario. The hashing
  approach encodes tokens with the 32-bit Blake2b digest
  and projects them into a fixed 384-dimensional vector via
  signed modular reduction, then L2-normalises the result.
  The model_version is `hashing-1.0.0` and the license
  identifier is `Apache-2.0`; the entry passes the
  `LicenseGate` allow-list (no review required).

- `MultilingualSentenceTransformerEmbeddingModel`
  (opt-in) — the
  `paraphrase-multilingual-MiniLM-L12-v2` model (Apache-2.0
  weights, Apache-2.0 runtime) via the optional
  `sentence-transformers` Python package. Registered only
  when the `sentence-transformers` extra is installed AND
  `project-context.yaml:embedding.backend ==
  "multilingual-st"`. The expected dimension is 384.

The active adapter is selected through
`project-context.yaml:embedding.backend`. The default is
`hashing`; the multilingual semantic backend is `multilingual-st`.

## Alternatives considered

- **Non-multilingual BERT variants** (e.g.
  `bert-base-uncased` English-only) — rejected because
  they fail the §25 multilingual coverage requirement and
  degrade DE / UK / RU retrieval quality.
- **GPU-only models** (e.g. `bge-large-en-v1.5` in
  fp16-only deployments) — rejected because they violate
  the §25 "CPU-capable deployment" requirement.
- **Non-Apache / non-MIT model licenses** (e.g.
  OpenAI `text-embedding-3-*` proprietary weights, Cohere
  commercial weights without redistribution rights) —
  rejected because they fail the §5.1 preferred license
  policy and would require `LicenseGate` review with no
  advantage over the Apache-2.0 multilingual sentence-
  transformers candidate.
- **ONNX Runtime-only deployments** without a Python
  `sentence-transformers` package — deferred to a future
  ADR; the multilingual-st adapter currently requires the
  Python `sentence-transformers` runtime. ONNX support
  ships as a follow-up adapter when the §9 enterprise
  profile requires it.
- **`colbert-ai` for embeddings** — rejected; ColBERT-style
  late interaction is a reranker, not an embedding model,
  and the §30 reranker port already covers it.

## Consequences

Positive:

- The default `HashingEmbeddingAdapter` boots on a CPU-only
  machine without a GPU, a model download or a network call.
  The stdlib-only fallback satisfies the §25
  "CPU-capable deployment" scenario AND the §33 retrieval-
  first escalation principle (cheapest deterministic
  retrieval mechanism available).
- The opt-in multilingual sentence-transformer adapter
  provides real semantic quality for DE / EN / UK when the
  enterprise-scale profile enables it through configuration.
- Both adapters expose the same `EmbeddingModelPort` surface,
  so Phase 3 (`DenseIndexPort.index_chunk`) and Phase 4
  (`HybridRetrievalPort.query`) consume the vectors without
  knowing the active backend.
- Both adapters are registered against the
  `distribution/licenses/dependency-inventory.json` SPDX
  inventory; the `LicenseGate` accepts the entries without
  review.

Negative:

- The hashing adapter is not a real semantic embedding
  model. It is a deterministic fallback that satisfies the
  "same-dimension vector" check; it does not produce
  high-quality multilingual semantic similarity. Operators
  who require semantic quality must opt into
  `multilingual-st`.
- The multilingual sentence-transformer adapter is opt-in
  because the model weights require a network download and
  a Python runtime. The default `Containerfile` ships
  without the `sentence-transformers` extra so the image
  stays small; the documented Containerfile snippet
  enables the extra in a derived image.

## Compliance

- `python -m unittest tests.test_platform_phase4
  .EmbeddingModelTests -v` — passes.
- `python -m pi_platform.cli license-gate` — passes with
  the new SPDX entries.
- `python -m pi_platform.cli embedding-status` — reports
  the active backend, dimension, model version and
  license identifier.

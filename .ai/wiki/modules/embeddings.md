---
id: modules.embeddings
title: Phase 4 embedding-model module map
kind: modules
status: active
summary: Phase 4 §25 embedding model — port, core and adapter layer for the multilingual, CPU-capable, replaceable embedding backend.
sourceRefs:
  - pi_platform/ports/retrieval/embedding_model.py
  - pi_platform/core/retrieval/embedding_model.py
  - pi_platform/adapters/retrieval/hashing_embedding_model.py
  - pi_platform/adapters/retrieval/multilingual_st_embedding_model.py
  - openspec/specs/2026-10-04-embedding-model/spec.md
  - openspec/changes/implement-phase-4-retrieval/proposal.md
maintenance:
  mode: authored
related:
  - modules.retrieval
  - adr.0009-embedding-model-selection
---

# Phase 4 embedding-model modules

The §25 embedding model exposes a multilingual, CPU-capable,
commercially-licensed, replaceable backend to the Phase 4 retrieval
pipeline and the Phase 3 `DenseIndexPort`. The default
implementation must run on a CPU-only machine without a GPU and
must support German (DE), English (EN) and Ukrainian (UK) at
parity, with Russian (RU) as an opt-in configuration.

The embedding layer ships as a port-and-adapter pair: the
`EmbeddingModelPort` under `pi_platform/ports/retrieval/`, the
`HashingEmbeddingModel` core under `pi_platform/core/retrieval/`,
and the `HashingEmbeddingAdapter` plus the opt-in
`MultilingualSentenceTransformerEmbeddingModel` adapter under
`pi_platform/adapters/retrieval/`.

## Port (`pi_platform/ports/retrieval/embedding_model.py`)

- `EmbeddingModelPort` — abstract base with the operations the
  §25 spec mandates: `embed`, `embed_batch`, `dimension`,
  `model_version`, `license_id`, `stats`. The
  `EmbeddingModelError` exception is raised when an adapter
  cannot satisfy a request.

## Core (`pi_platform/core/retrieval/embedding_model.py`)

- `HashingEmbeddingModel` — deterministic stdlib-only feature-
  hashing backend. Tokens are projected into a 384-dimensional
  vector via the 32-bit Blake2b digest and a signed modular
  reduction; the resulting vectors are L2-normalised so cosine
  similarity is a dot product. The implementation is the
  stdlib-only fallback the §25 spec requires so the platform can
  boot on a CPU-only machine without a GPU or a model download.

The hashing approach is multilingual-capable (DE / EN / UK / RU)
because the token regex matches Unicode word characters and
Cyrillic ideographs. It is NOT a substitute for a real semantic
embedding model — it is a deterministic, license-clean, dimension-
stable fallback that satisfies the §25 "fixed-dimension vector"
scenario and the §25 deterministic vectorisation scenario.

## Adapters (`pi_platform/adapters/retrieval/`)

- `HashingEmbeddingAdapter` — registry-friendly wrapper around
  `HashingEmbeddingModel`. The default backend selected by
  `embedding-status`; satisfies the §25 "preferred-license
  adapter" scenario with an `Apache-2.0` license identifier.
- `MultilingualSentenceTransformerEmbeddingModel` — opt-in adapter
  for the `paraphrase-multilingual-MiniLM-L12-v2` model
  (Apache-2.0 weights, Apache-2.0 runtime) via the optional
  `sentence-transformers` Python package. Registered only when
  the package is installed AND
  `project-context.yaml:embedding.backend == "multilingual-st"`.

## Selection

The active adapter is selected through
`project-context.yaml:embedding.backend`:

- `hashing` (default) — `HashingEmbeddingAdapter`. CPU-only,
  stdlib-only, deterministic, license-clean, dimension-stable.
- `multilingual-st` (opt-in) —
  `MultilingualSentenceTransformerEmbeddingModel`. Requires the
  `sentence-transformers` extra installed via the documented
  Containerfile snippet and the SPDX entry in
  `distribution/licenses/dependency-inventory.json`.

The decision is recorded in
[`adr.0009-embedding-model-selection`](../adr/0009-embedding-model-selection.md).

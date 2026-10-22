---
id: project.deployment-profiles
title: Deployment execution profiles (minimal, semantic-cpu, semantic-gpu, quality, contextualized, multimodal)
kind: project
status: active
summary: Configuration presets for embedding, reranking, contextualization, host acceleration, and multimodal figures without fork-specific code paths.
sourceRefs:
  - pi_platform/ports/retrieval/embedding_profile.py
  - pi_platform/core/control/multimodal.py
  - pi_platform/core/control/diagnostics/v0_8_panels.py
  - openspec/specs/2026-10-16-embedding-execution-profile/spec.md
maintenance:
  mode: authored
related:
  - architecture.embedding-profile-identity
  - modules.host-embedding-accelerator
  - project.retrieval-evaluation-corpus
---

# Deployment execution profiles

Plan §24 defines the following conceptual retrieval presets. These are not the
standalone kit's model/accelerator matrix or a claim that each preset was
exercised in a production container:

| Profile | Embedding profile | Reranker | Enrichment | Notes |
| --- | --- | --- | --- | --- |
| `minimal` | `HASHING_DEFAULT` | `Bm25LightRerankerAdapter` | deterministic | Zero-dependency default; Tier-1 CI baseline |
| `semantic-cpu` | `EMBEDDINGGEMMA2_512` | `CrossEncoderRerankerAdapter` (with fallback) | deterministic | Single-container CPU semantic retrieval |
| `semantic-gpu` | `EMBEDDINGGEMMA2_512` | `CrossEncoderRerankerAdapter` | deterministic | Earlier host-accelerator preset; standalone kit uses explicit GGUF selection without silent GPU fallback |
| `quality` | `QWEN3_EMBEDDING_0_6B_1024` | `Qwen3RerankerAdapter` (with fallback) | deterministic | Separate 1024-dim ANN namespace |
| `contextualized` | `EMBEDDINGGEMMA2_512` | quality / fast | `LocalContextualizer` (`InferencePolicy.LOCAL_MODEL_ALLOWED`) | Indexing-time inferred context cached by `ContextualizationCache` |
| `multimodal` | `MULTIMODAL_FIGURE_512` | quality / fast | deterministic + figure captions | Gated by `multimodal.figures` feature flag (off by default) |

Active profile status is surfaced through the six Control Plane panels in `pi_platform/core/control/diagnostics/v0_8_panels.py`.

[EmbeddingProfile identity](../architecture/embedding-profile-identity.md) ·
[Host embedding accelerator](../modules/host-embedding-accelerator.md)

## Standalone kit model and device selection

| Model | CPU | Vulkan / CUDA |
|---|---|---|
| `qwen` | Native PyTorch; default | Pinned Qwen GGUF |
| `gemma` | Native PyTorch, text/images | Pinned Gemma GGUF plus projector, text/images |
| `qwen-gguf` / `gemma-gguf` | Explicit CPU sidecar | Corresponding GPU runtime |

Set `PI_EMBEDDING_MODEL` and `PI_ACCELERATOR` in `deployment.env`. GPU inference
uses a Linux sidecar or a Windows native service. Docling runs on CPU in every
profile. The kit does not automatically activate the conceptual reranker or
contextualization presets above. See [deployment architecture](../architecture/portable-deployment.md)
for setup, vector isolation, failure behavior and verification limits.

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

Plan §24 defines six deployment profiles as configuration presets over the same ports and adapters:

| Profile | Embedding profile | Reranker | Enrichment | Notes |
| --- | --- | --- | --- | --- |
| `minimal` | `HASHING_DEFAULT` | `Bm25LightRerankerAdapter` | deterministic | Zero-dependency default; Tier-1 CI baseline |
| `semantic-cpu` | `EMBEDDINGGEMMA2_512` | `CrossEncoderRerankerAdapter` (with fallback) | deterministic | Single-container CPU semantic retrieval |
| `semantic-gpu` | `EMBEDDINGGEMMA2_512` | `CrossEncoderRerankerAdapter` | deterministic | Uses optional host accelerator (`HostEmbeddingClient`) with CPU fallback |
| `quality` | `QWEN3_EMBEDDING_0_6B_1024` | `Qwen3RerankerAdapter` (with fallback) | deterministic | Separate 1024-dim ANN namespace |
| `contextualized` | `EMBEDDINGGEMMA2_512` | quality / fast | `LocalContextualizer` (`InferencePolicy.LOCAL_MODEL_ALLOWED`) | Indexing-time inferred context cached by `ContextualizationCache` |
| `multimodal` | `MULTIMODAL_FIGURE_512` | quality / fast | deterministic + figure captions | Gated by `multimodal.figures` feature flag (off by default) |

Active profile status is surfaced through the six Control Plane panels in `pi_platform/core/control/diagnostics/v0_8_panels.py`.

[EmbeddingProfile identity](../architecture/embedding-profile-identity.md) ·
[Host embedding accelerator](../modules/host-embedding-accelerator.md)

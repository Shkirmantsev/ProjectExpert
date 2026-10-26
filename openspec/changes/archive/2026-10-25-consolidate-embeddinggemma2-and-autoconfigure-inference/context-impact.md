# Context impact — EmbeddingGemma 2 consolidation and portable inference runtime

## Specs

| Spec | Action |
|---|---|
| `2026-10-04-embedding-model` | modify — one production model |
| `2026-10-16-embedding-execution-profile` | modify — fingerprint covers the projector and the quantisation; the backend is not part of the identity |
| `2026-10-18-real-embeddinggemma2-binding` | modify — the projector is part of the pinned package; modalities are discovered, not assumed |
| `2026-10-18-real-qwen3-embedding-binding` | remove — the capability is retired |
| `2026-10-11-one-click-distribution` | modify — automatic backend selection, GPU downgrade instead of failure, launcher parity |
| `portable-inference-runtime` | add — new capability |

On adoption, `2026-10-18-real-qwen3-embedding-binding` is removed from
`openspec/CURRENT.md` and `portable-inference-runtime` is added.

## Wiki

| Node | Action |
|---|---|
| `modules.inference-runtime` | create — the inference runtime package, the selection policy and the degradation path |
| `interfaces.one-command-ux` | update — the automatic backend selection and the retired model alias |
| `modules.release-gate` | update — the capability matrix states what was verified on CPU-only hardware |
| `modules.retrieval-runtime` | update — the model registry no longer offers a second production model |

## ADR

A new ADR is required: the native inference engine stays a separate, optional,
supervised process and is not linked into the application process; the platform
ships one embedding model; the GPU is an optimisation, never a startup
prerequisite.

## Not affected

* The canonical Git knowledge schema.
* The retrieval architecture, the sparse index and the dense index contract.
* The MCP protocol surface.
* The harness behaviour of this repository.
* ROCm / HIP support, which remains out of scope.

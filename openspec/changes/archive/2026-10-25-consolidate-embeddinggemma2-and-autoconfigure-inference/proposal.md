# Consolidate EmbeddingGemma 2 and autoconfigure the inference runtime

## Why

The previous review left three product-level gaps and one architectural gap.

* The default deployment still ships **Qwen3-Embedding-0.6B Q4_K_M** from a
  third-party fork (`openmycel/Qwen3-Embedding-0.6B-GGUF`). It is text-only,
  it is a third-party artefact rather than an upstream conversion, and it
  forces a 1024-dimensional vector space that is not used anywhere else.
* The **multimodal package** is not actually exercised. `mmproj` was wired
  into one Compose overlay, but the deployment default never loaded it and no
  test proved that image, audio or video embeddings work.
* **Backend selection is manual.** `PI_ACCELERATOR` must be set to `cpu`,
  `vulkan` or `cuda` by hand. When the selected backend is unavailable the
  launcher aborts instead of falling back, so a workstation with an office
  graphics driver, an integrated GPU, or no GPU at all needs a different
  manual procedure per machine.
* There is **no single source of truth** for inference flags. Flags are
  spread over `LLAMA_ARG_*` environment variables whose names differ from the
  llama.cpp flag names (`--batch-size` is `LLAMA_ARG_BATCH`, `--ubatch-size`
  is `LLAMA_ARG_UBATCH`, `--parallel` is `LLAMA_ARG_N_PARALLEL`). Two
  variables in the current deployment (`LLAMA_ARG_BATCH_SIZE`,
  `LLAMA_ARG_UBATCH_SIZE`) are silently ignored, so the requested batch
  policy never reaches the runtime.

The operator wants one reliable model, a working multimodal package, and a
deployment that starts correctly on Windows and Linux with CUDA, Vulkan, an
integrated/office graphics driver, or CPU only, without manual per-machine
tuning.

## What changes

* **EmbeddingGemma 2 becomes the only embedding model.** The Qwen embedding
  profile, adapter, aliases, setup options, licence records and deployment
  entries are removed. `gemma` resolves to the pinned **Q8_0** GGUF
  backbone plus the **Q8_0 multimodal projector** and becomes the default
  everywhere (CLI, settings, Compose, licence inventory). The native
  `sentence-transformers` binding stays available only as an explicit,
  non-default opt-in (`gemma-torch`).
* **Multimodal is a first-class, verified capability.** The runtime loads the
  projector by default, the adapter accepts image, audio and video inputs,
  and the modalities that a given runtime actually supports are discovered
  from the runtime itself instead of being assumed.
* **One inference runtime policy in Python.** A new `pi_platform/core/inference`
  package owns backend discovery, device selection, the launch plan and the
  degradation policy. The Bash and PowerShell launchers become thin wrappers
  that call it.
* **Automatic backend selection with CPU fallback.** The launcher probes the
  candidate backends in order (CUDA, then Vulkan, then CPU), validates the
  device with the runtime's own `--list-devices`, rejects software
  rasterisers, and selects the best validated device. A failed or unavailable
  GPU candidate degrades to the validated CPU profile instead of aborting.
* **Explicit runtime flags.** The launch plan is emitted as an explicit
  argument vector instead of relying on environment variables whose names are
  llama.cpp-version-specific.

## Impact

Affects the embedding model port and profile registry, the embedding adapter
and factory, the retrieval settings and runtime configuration resolver, the
CLI, the licence inventory, the OpenSpec capability
`real-qwen3-embedding-binding` (retired), the deployment kit and the Compose
topology.

* **Compatibility:** existing vector namespaces are unaffected — the Gemma
  GGUF profile has its own identity, so switching from Qwen to Gemma creates
  a new namespace and triggers one reindex. Operators who persisted
  `PI_EMBEDDING_MODEL=qwen-gguf` must change it to `gemma`; the launcher
  reports the retired alias explicitly instead of silently substituting.
* **Migration:** the retired Qwen aliases are rejected with an actionable
  message. No vector data is deleted; the previous namespace stays on disk
  until the operator prunes it.
* **New capability:** `portable-inference-runtime`.
* **Wiki:** `modules.inference-runtime`, `interfaces.one-command-ux`,
  `modules.release-gate`.
* **Not claimed:** ROCm/HIP support is explicitly out of scope, and no GPU
  configuration is certified by CPU-only verification.

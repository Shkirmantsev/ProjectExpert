# Tasks — EmbeddingGemma 2 consolidation and portable inference runtime

## Phase 1 — Model consolidation

- [x] `pi_platform/adapters/retrieval/gguf_artifacts.py`: keep only the
      pinned EmbeddingGemma 2 Q8_0 backbone and Q8_0 projector; remove the
      Qwen artefacts; expose the quantisation, pooling and dimension
      constants.
- [x] `pi_platform/ports/retrieval/embedding_profile.py`: remove the Qwen
      profile and registry entry; add the Gemma GGUF profile whose identity
      covers repository, revision, both checksums, quantisation, pooling,
      normalisation and dimensions.
- [x] `pi_platform/adapters/retrieval/embedding_model_factory.py`: make
      `gemma` resolve to the GGUF binding; add `gemma-torch`; remove every
      Qwen alias and the `gemma-gguf` spelling.
- [x] `pi_platform/core/control/retrieval_settings.py`: restrict the
      production model choices to the Gemma family.
- [x] `pi_platform/adapters/config/runtime_configuration_resolver.py`:
      restrict the production aliases and reject the retired aliases with an
      actionable message.
- [x] `pi_platform/cli/main.py`: restrict the model choices, the `models`
      subcommands and the first-start defaults.
- [x] `pi_platform/cli/gguf_setup.py`: download only the Gemma backbone and
      projector; verify both checksums.
- [x] `distribution/licenses/model-licenses.json`: record the Gemma GGUF
      artefacts with their checksums; demote the retired model to a
      non-production record with a rationale.
- [x] Remove the retired adapter module and its references.

## Phase 2 — Multimodal

- [x] Extend the embedding request port with audio and video inputs.
- [x] `pi_platform/adapters/retrieval/llama_cpp_embedding_model.py`: shape
      image, audio and video requests for the runtime; discover the
      advertised input modalities from the runtime; refuse an unsupported
      modality explicitly; keep the Matryoshka truncation and the
      re-normalisation.
- [x] Load the projector by default in every deployment profile.
- [x] Bound the video path: frame-rate and duration caps and a physical batch
      floor, so a video request fails as a bounded input error rather than an
      internal server error.

## Phase 3 — Inference runtime policy

- [x] `pi_platform/core/inference/backend.py`: backend value type, device
      naming, candidate ordering, capability flags.
- [x] `pi_platform/core/inference/device_probe.py`: parse the runtime device
      list; classify software rasterisers; run a bounded probe.
- [x] `pi_platform/core/inference/profile.py`: the selection policy, CPU
      baseline first, rejection reasons, degradation.
- [x] `pi_platform/core/inference/launch.py`: build the explicit runtime
      argument vector and the Compose fragments for a profile.
- [x] `pi_platform/cli/inference.py`: the `inference doctor`, `inference plan`
      and `inference status` commands, wired into the CLI.

## Phase 4 — Deployment integration

- [x] `distribution/deployment/accelerator-lock.json`: Gemma-only model
      records; add the CPU runtime artefacts for Windows and Linux.
- [x] `distribution/deployment/compose.*.yaml`: Gemma backbone and projector
      by default; explicit runtime arguments; the projector off the GPU.
- [x] `distribution/deployment/compose.sh`: probe the candidate backends,
      apply the decision, fall back to CPU.
- [x] `distribution/deployment/compose.ps1` and
      `setup-windows-accelerator.ps1`: the same duty list on Windows; the
      native runtime is selected automatically.
- [x] `distribution/deployment/deployment.env`: the new defaults.
- [x] `distribution/deployment/README.md`: the new model table and the
      automatic backend behaviour.

## Phase 5 — Verification

- [x] Unit tests for the selection policy, the device-list parser and the
      argument builder, including the software-rasteriser and
      unavailable-GPU cases.
- [x] A real-inference test that starts the pinned runtime with the pinned
      backbone and projector and asserts a valid normalised vector for text,
      image and audio, and a bounded error for video. (The pinned runtime was
      exercised directly for this change: text, image, audio AND video all
      returned valid 768-dimensional unit-norm vectors; the repository test is
      opt-in through PI_RUN_MULTIMODAL_TESTS=1.)
- [x] Regression tests for the retired aliases and the new default.
- [x] Deployment launcher tests for the automatic backend selection.
- [x] `python harness.py check`.

## Phase 6 — Documentation and state

- [x] Update the Wiki nodes for the inference runtime and the deployment.
- [x] Update `openspec/CURRENT.md` when the change is adopted.
- [x] Record the verified capability matrix, including what was physically
      tested and what remains conditional on hardware that was not available.

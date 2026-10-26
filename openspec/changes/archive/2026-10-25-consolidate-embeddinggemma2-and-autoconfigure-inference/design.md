# Design — EmbeddingGemma 2 consolidation and portable inference runtime

## 1. Verified baseline facts

These were established by direct measurement in this repository and are the
basis for the design. They are not assumptions.

### 1.1 Model artefacts (verified against the Hugging Face API)

| Artefact | Repository | Revision | SHA-256 | Verified |
|---|---|---|---|---|
| `embeddinggemma-2-Q8_0.gguf` (310 MB) | `ggml-org/embeddinggemma-2-GGUF` | `58faf90940886df2d62be555c8765d00dac362c5` | `2188ac1d…b09135` | yes, downloaded and hashed |
| `mmproj-embeddinggemma-2-Q8_0.gguf` (555 MB) | `ggml-org/embeddinggemma-2-GGUF` | same | `c4a8a526…b64f` | yes, downloaded and hashed |

`unsloth/embeddinggemma-2` was evaluated and **rejected as a runtime
source**: it publishes `model.safetensors` (1.49 GB, full precision) plus a
tokenizer and no GGUF and no projector. It is a Transformers checkpoint, not
a `llama.cpp` artefact, and it cannot serve the portable CPU/CUDA/Vulkan
runtime. The Q8_0 quantisation the operator asked for is supplied by
`ggml-org/embeddinggemma-2-GGUF`, and the repository already pinned exactly
those two Q8_0 files with matching checksums. The change therefore keeps the
existing pin and removes the Qwen pin.

### 1.2 Multimodal capability (verified by real inference)

The `mmproj-embeddinggemma-2-Q8_0.gguf` header was parsed directly:

```
clip.has_vision_encoder = True    clip.vision.projector_type = gemma4v
clip.has_audio_encoder  = True    clip.audio.projector_type  = gemma4a
```

llama.cpp `b11515` implements `PROJECTOR_TYPE_GEMMA4V` and
`PROJECTOR_TYPE_GEMMA4A`, so both encoders are live. Running the pinned
server image with the pinned weights produced:

```
/v1/models → architecture.input_modalities = ["text","image","audio","video"]
/v1/embeddings → text  OK  dim=768 norm=1.000000
                → image OK  dim=768 norm=1.000000
                → audio OK  dim=768 norm=1.000000
                → video FAIL 500 "input (681 tokens) is too large to process
                                  (current batch size: 512)"
```

Video is therefore supported by the runtime but needs a physical batch that
fits the decoded frame tokens. Video handling is bounded explicitly
(frame-rate and duration caps plus a physical-batch floor) rather than being
declared and left to fail at request time.

### 1.3 llama.cpp environment-variable traps

`llama-server` reads `LLAMA_ARG_*` variables, but the variable name is an
explicit per-argument annotation and frequently differs from the flag name:

| Flag | Environment variable |
|---|---|
| `--batch-size` | `LLAMA_ARG_BATCH` |
| `--ubatch-size` | `LLAMA_ARG_UBATCH` |
| `--ctx-size` | `LLAMA_ARG_CTX_SIZE` |
| `--parallel` | `LLAMA_ARG_N_PARALLEL` |
| `--n-gpu-layers` | `LLAMA_ARG_N_GPU_LAYERS` |
| `--device` | `LLAMA_ARG_DEVICE` |
| `--pooling` | `LLAMA_ARG_POOLING` |
| `--mmproj` | `LLAMA_ARG_MMPROJ` |
| `--mmproj-offload` | `LLAMA_ARG_MMPROJ_OFFLOAD` / `LLAMA_ARG_NO_MMPROJ_OFFLOAD` |

Booleans are negated with a `LLAMA_ARG_NO_` prefix, and any command-line
argument overrides the environment. The current deployment sets
`LLAMA_ARG_BATCH_SIZE` and `LLAMA_ARG_UBATCH_SIZE`, which are **not read** —
confirmed by the server log reporting the default `n_batch 2048 /
n_ubatch 512` after those variables were set to 1024.

**Decision:** the runtime flags are emitted as an explicit argument vector.
Environment variables are not used for inference flags.

## 2. Model identity

One model, two execution bindings, one vector space.

| Alias | Binding | Default | Notes |
|---|---|---|---|
| `gemma` | pinned GGUF Q8_0 + Q8_0 projector through `llama.cpp` | **yes** | portable across Windows/Linux and CPU/CUDA/Vulkan; multimodal |
| `gemma-torch` | `sentence-transformers` on `google/embeddinggemma-2` | no | explicit opt-in; text and image only; requires `torch` |
| `hashing` | deterministic hash projection | no | `minimal` startup profile only |

Retired: `qwen`, `qwen-gguf`, `qwen3`, `qwen3-embedding-0.6b`, and the
`gemma-gguf` spelling (folded into `gemma`).

Both Gemma bindings keep their own `EmbeddingProfile`, therefore their own
identity key and their own ANN namespace. The GGUF binding is the default
because it is the only binding that satisfies the whole hardware matrix.

Output shape: the runtime returns 768 dimensions; the adapter applies
Matryoshka truncation to 512 and re-normalises, exactly as the existing
`EMBEDDINGGEMMA2_512` profile declares.

## 3. Inference runtime package

New package `pi_platform/core/inference`:

| Module | Responsibility |
|---|---|
| `backend.py` | `InferenceBackend` value type (`cpu`, `cuda`, `vulkan`), device names, ordering, capability flags |
| `device_probe.py` | parse `--list-devices` output; classify software rasterisers; run a bounded probe |
| `profile.py` | `InferenceProfile` (backend, device, flags) and the selection policy |
| `launch.py` | build the `llama-server` argument vector and the Compose fragments for a profile |
| `supervisor.py` | optional supervised child process with bounded retry and quarantine |

All decision logic is pure and hardware independent so it is unit-testable
without a GPU. Only `device_probe` touches the outside world, and it does so
through a bounded subprocess with a timeout.

### 3.1 Selection policy

```
CPU baseline is always probed first and must succeed.
Then, in order: CUDA → Vulkan → (UMA/integrated only if explicitly allowed).
A candidate is rejected when:
  - the probe times out or exits non-zero,
  - the runtime reports no device for the requested backend,
  - the only device is a software rasteriser (lavapipe / SwiftShader),
  - the device is an unknown-memory UMA device and hybrid mode is not explicitly allowed.
The first validated candidate wins. If no GPU candidate validates, the CPU
profile is used. A GPU failure never fails the application.
```

This is the plan's §5.2 order. The policy differs from the current launcher
in one decisive way: **an unavailable GPU is a downgrade, not an error**.

### 3.2 Flag policy

| Profile | Flags |
|---|---|
| CPU | `--device none --no-mmproj-offload --ctx-size 2048 --batch-size 256 --ubatch-size 512 --parallel 1 --pooling mean --embd-normalize 2` |
| GPU | `--device <probed> --no-mmproj-offload --fit on --fit-target <mib> --ctx-size 2048 --batch-size 1024 --ubatch-size 1024 --parallel 1 --pooling mean --embd-normalize 2` |

The multimodal projector always stays on the CPU by default (`§1` objective 5),
because a 555 MB Q8 projector plus runtime buffers does not fit a small UMA
allocation safely.

The physical batch floor of 512 is the value the runtime needs for an image;
video needs more, so the video path requests the GPU/CPU-appropriate floor and
caps frames instead of failing at request time.

## 4. Deployment integration

The Python package is the only place that decides anything. The launchers
collect evidence and apply the decision.

### 4.1 Linux (Docker)

`compose.sh` collects probe evidence by asking each candidate runtime image
for its device list, passes the evidence to
`python -m pi_platform.cli inference plan`, and applies the resulting
profile by exporting the selected device and flags into the Compose
environment. The application container therefore receives the resolved plan
through ordinary Compose interpolation.

### 4.2 Windows (native runtime)

`compose.ps1` / `setup-windows-accelerator.ps1` download the pinned native
`llama-server` for the candidate backend, probe it with `--list-devices`,
and apply the same decision. The native service is the existing
`host.docker.internal:8769` topology; only the selection becomes automatic.

### 4.3 Degradation

| Event | Result |
|---|---|
| no GPU candidate validates | CPU profile, application keeps running |
| GPU runtime fails to start | child is stopped, backend is quarantined for the session, CPU profile is used |
| model files missing or hash mismatch | explicit provisioning error; the application still starts |
| runtime absent entirely | sparse-only retrieval, application still starts |

## 5. Multimodal adapter

`LlamaCppEmbeddingModel` gains:

* `EmbeddingRequest` support for `image_path`, `audio_path` and `video_path`;
* request shaping for the llama.cpp structured content format
  (`image_url`, `input_audio`, `input_video`);
* a **capability probe** that reads the runtime's advertised
  `input_modalities` from `/v1/models` instead of assuming a modality works;
* an explicit error when a caller requests a modality the runtime does not
  advertise.

The adapter never substitutes a hash vector, a zero vector, or OCR text for a
missing modality. A missing modality is reported as unavailable.

## 6. Data and index safety

* The Gemma GGUF profile is a new `EmbeddingProfile` identity, so it gets a
  new ANN namespace. Qwen vectors are never merged into it.
* Retiring the Qwen aliases does not delete any index. The old namespace stays
  on disk until the operator prunes it.
* The model fingerprint (repository, revision, both SHA-256 values,
  quantisation, pooling, normalisation, dimensions) is part of the profile
  identity, so a changed projector forces a reindex rather than a silent
  mismatch.

## 7. Out of scope

* ROCm / HIP support (explicitly excluded by the operator).
* Installing or upgrading system drivers, the CUDA toolkit or a Vulkan SDK.
* Guaranteeing recovery from an operating-system level driver crash.
* Rewriting the retrieval architecture.

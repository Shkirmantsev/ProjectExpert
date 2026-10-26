# Project Intelligence deployment

Run `bash start.sh` on Linux or `powershell -File start.ps1` on Windows.
Alternatively run `make platform-start` (GNU Make required). Windows uses
Docker Desktop with WSL2 and Linux containers. Docker Compose 2.30+ is required
for the optional CUDA profile; the CPU profile needs Compose 2.20+.

The target repository defaults to the parent directory. Set PI_TARGET_REPO in
`deployment.env` to change it; use forward slashes for Windows paths. The target
must already exist. First startup downloads the selected embedding model. The
default EmbeddingGemma 2 artifact is ~310 MB and its multimodal projector is
~555 MB; PDF layout/table/OCR assets download only when PDFs are present.
Allow network access; the launcher timeout is 30 minutes, not an expected startup duration. The launcher reports success only after retrieval readiness.

## Models and hardware

ProjectExpert ships **one** embedding model: **EmbeddingGemma 2**, quantised
`Q8_0`, served by a pinned `llama.cpp` runtime. The pinned package is the
`Q8_0` backbone **plus** the `Q8_0` multimodal projector, so text, image,
audio and video embeddings are all available. The retired alternative
embedding model is no longer selectable, is no longer a setup option and is
not part of any deployment profile.

| PI_EMBEDDING_MODEL | Execution |
|---|---|
| gemma (default) | pinned EmbeddingGemma 2 Q8_0 GGUF (backbone + projector) through the managed `llama.cpp` runtime |
| gemma-torch | native Transformers binding of the same checkpoint; explicit opt-in; text and image only; needs `torch` |

### Automatic backend selection

`PI_ACCELERATOR=auto` (the default) detects the backend on the machine and
starts the deployment with the best **validated** profile:

```
CUDA  ->  Vulkan  ->  CPU
```

The order is a preference, not a requirement. A candidate is only selected
when the runtime itself proves it can use a device: the launcher asks the
runtime for its device list and the device must be reported. A software
rasteriser (lavapipe, SwiftShader) is never selected, and the multimodal
projector always stays on the CPU because its ~555 MB of Q8 weights plus
runtime buffers do not fit a small integrated-GPU allocation safely.

**A GPU that is not measurably faster is also not selected.** The GPU is an
optimisation, so the launcher measures it: the CPU baseline and every
validated GPU candidate are started, measured with the same fixed corpus and
stopped again before the winner is started for real. A GPU candidate is only
selected when it is at least **1.10x faster** than the CPU baseline. A GPU
that works but is slower is rejected with that reason and the CPU profile is
used.

**An unavailable or unusable GPU is a downgrade, not a failure.** The
deployment falls back to the validated CPU profile, reports which candidates
were rejected and why, and keeps serving. The same is true for an explicitly
selected backend that does not validate. An explicitly selected backend is the
operator's decision and is not second-guessed by the benchmark.

| Host | Selected |
|---|---|
| NVIDIA GPU with a working driver / container toolkit | CUDA |
| NVIDIA GPU without the container toolkit, or an AMD/Intel GPU with a Vulkan driver | Vulkan |
| Integrated / office graphics driver, or no GPU | CPU |

The CPU profile is the reference mode and never requires a GPU driver, the
CUDA toolkit or a Vulkan SDK. The launcher never installs or upgrades drivers.

`PI_ACCELERATOR` may still be set to `cpu`, `vulkan` or `cuda` to skip the
detection; an explicit choice that does not validate still degrades to CPU.
`PI_GPU_DEVICE` pins a specific device (for example `Vulkan1` or `CUDA1`); it
is honoured only when the runtime actually reported that device.

### What is supported and what is not

* **ROCm / HIP is not supported.** There is no AMD ROCm backend, and no ROCm
  runtime is shipped or downloaded. An AMD GPU is served through Vulkan when
  a Vulkan driver is present, otherwise through the CPU profile.
* No CUDA toolkit, Vulkan SDK or driver is ever installed on a client
  machine. The Linux GPU profiles use the pinned official runtime images; the
  Windows GPU profile uses the pinned native release archive.
* The runtime flags are passed as an explicit argument vector. The
  `LLAMA_ARG_*` environment variables are deliberately **not** used for
  inference flags: llama.cpp's variable names differ from its flag names
  (`--batch-size` is `LLAMA_ARG_BATCH`, `--ubatch-size` is `LLAMA_ARG_UBATCH`,
  `--parallel` is `LLAMA_ARG_N_PARALLEL`) and a wrong name is silently
  ignored.

### Physically verified vs. conditional

| Configuration | Status |
|---|---|
| Linux, CPU only, `llama.cpp` b11515 | **verified**: real inference, text + image + audio + video embeddings, 768-dimensional unit-norm vectors |
| Linux, Vulkan (AMD integrated GPU) | **verified**: the device is detected, the runtime offloads to it, all four modalities return valid vectors, and the CPU/Vulkan parity gate passes |
| Linux, automatic backend selection | **verified**: the launcher probes, measures and selects; on the verification host it correctly rejected a working-but-slower Vulkan profile |
| Linux, CUDA | conditional: the runtime image, the device selection and the `--fit` budget are implemented and probed, but no NVIDIA hardware was available for this verification |
| Windows, any backend | conditional: the launcher implements the same duty list and the native runtime is pinned, but no Windows host was available for this verification |

### Measured on the verification host

AMD Radeon Graphics (RADV RENOIR), integrated GPU, 512 MiB dedicated VRAM
carve-out, Mesa 25.2.8, Vulkan 1.4.318, llama.cpp b11515:

| Measurement | Value |
|---|---|
| Device reported by `--list-devices` | `Vulkan0: AMD Radeon Graphics (RADV RENOIR) (32334 MiB, 30768 MiB free)` |
| CPU / Vulkan cosine parity (text, image, audio, video) | 0.999945 / 0.999929 / 0.999911 / 0.999953 (gate: >= 0.995) |
| Vulkan embedding latency (median of 30) | 30.77 ms -> 32.50 emb/s |
| CPU embedding latency (median of 30) | 22.19 ms -> 45.06 emb/s |
| Measured speed-up | 0.72x -- **below the 1.10x gate, so the CPU profile is selected** |

The integrated GPU produces numerically equivalent embeddings but is slower
than the CPU for this workload, so the automatic selection keeps the CPU
profile. The Vulkan profile itself remains available and is used when the
operator selects it explicitly.

See `tmp/local/mm-run/evidence.md` in the development repository for the raw
measurements behind these statements.

### Windows specifics

Windows uses Docker Desktop with Linux containers. The CPU profile runs the
managed sidecar container. When a GPU candidate validates, a pinned **native**
`llama-server` is started on the host instead, and the application reaches it
through `host.docker.internal:8769`; it does not require Vulkan passthrough
into Docker. The native service listens on 127.0.0.1 with a per-run bearer
token stored in `accelerator/llama-api-key`; the token is never printed.
Permit access only from Docker/WSL in Windows Firewall, not public networks.
Run `powershell -File stop.ps1` before switching models or backends, then
start again. Linux uses `make platform-stop` before switching.

### Cache and maintenance

CPU/model state persists in the model-cache volume. Windows GPU assets persist
in accelerator/. Linux GPU weights share model-cache. `make platform-stop`
keeps caches. Never use `down -v` unless deleting cached assets intentionally.

Use `make platform-models`, `make platform-doctor`, `make platform-reindex`,
`make platform-logs`, `make eval`, `make eval-retrieval`, or
`make eval-chunk-size-sweep`. Eval targets use the bundled fixture benchmark;
repository evaluation requires a repository-specific golden set. The UI defaults
to http://localhost:8765, bound to loopback. Materialisation needs APPROVAL_TOKEN.

Published kits pin the tested application image digest and pinned accelerator
assets. To upgrade, export a new kit into a separate directory, compare files,
then update your existing kit deliberately. Export never overwrites your files.
SHA tags are retained without an automatic expiry/cleanup job. Registry owners
can delete packages; keep a local archive if permanent independent retention
is required. Files also live in Git under distribution/deployment/.

## Diagnostics

The inference runtime has its own diagnostic commands:

```bash
# inside the application container
python -m pi_platform.cli inference doctor --evidence-b64 <base64>
python -m pi_platform.cli inference plan --evidence-b64 <base64>
python -m pi_platform.cli inference status
```

`plan` prints exactly one JSON object: the selected backend and device, the
fit budget, every rejected candidate with its reason, the runtime argument
vector and the Compose environment fragment. The launchers use the same
command, so the Linux and Windows launchers cannot drift apart.

## Recovery and cache maintenance

Refresh failures retry without another source edit. Real edits made during indexing
keep readiness false until a coherent pass completes. Generated `distribution/sbom/`
files are excluded; other distribution source files remain indexed.

MCP clients should use Streamable HTTP at `/mcp`. GET returns 405 (no standalone
SSE stream); initialize and tools/list use POST. The endpoint is not a legacy SSE URL.

Native Hugging Face downloads and `models pull/verify` share `PI_MODEL_CACHE/hub`.
To reclaim abandoned partial downloads from either the old or current layout:

```bash
bash compose.sh exec -T production python -m pi_platform.cli models prune-incomplete
```

This removes only `.incomplete` blobs older than 24 hours whose downloader lock
can be acquired. Completed weights and active downloads are retained. Setup
removes its temporary file on failed downloads. The Gemma Q8_0 package has a
distinct vector profile from the retired model; upgrading rebuilds the vectors
once. Existing kits preserve their configuration on export: copy the updated
launcher/Compose files and deliberately set `PI_EMBEDDING_MODEL=gemma` when
upgrading.

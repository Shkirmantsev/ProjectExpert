# Project Intelligence deployment

Run `bash start.sh` on Linux or `powershell -File start.ps1` on Windows.
Alternatively run `make platform-start` (GNU Make required). Windows uses
Docker Desktop with WSL2 and Linux containers. Docker Compose 2.30+ is required
for the optional CUDA profile; the CPU profile needs Compose 2.20+.

The target repository defaults to the parent directory. Set PI_TARGET_REPO in
`deployment.env` to change it; use forward slashes for Windows paths. The target
must already exist. First startup downloads the selected embedding model. The default Qwen Q4_K_M
artifact is 396 MB; PDF layout/table/OCR assets download only when PDFs are present.
Allow network access; the launcher timeout is 30 minutes, not an expected startup duration. The launcher reports success only after retrieval readiness.

## Models and hardware

Select the model and backend independently in `deployment.env`:

| PI_EMBEDDING_MODEL | PI_ACCELERATOR | Execution |
|---|---|---|
| qwen-gguf | cpu | Qwen Q4_K_M CPU sidecar (default) |
| qwen | cpu | Qwen PyTorch CPU, explicit full-precision option |
| gemma | cpu | Gemma PyTorch CPU, text and images |
| qwen | vulkan or cuda | Qwen GGUF GPU |
| gemma | vulkan or cuda | Gemma GGUF GPU, text and images |

Run the same start command after editing the file. GPU choices automatically
select the corresponding GGUF model; Gemma also downloads its multimodal
projector. CPU operation never requires a discrete GPU or special GPU driver.
To select a GGUF model on CPU, use `qwen-gguf` or
`gemma-gguf` with `PI_ACCELERATOR=cpu`; this starts a CPU sidecar on both OSes.
Changing PyTorch/GGUF profiles rebuilds vectors in a separate namespace.

Gemma's PyTorch model access may require accepting provider terms and exporting
HF_TOKEN in your shell. Never store credentials in deployment files. Audio/video
embedding is not exposed. Docling OCR still runs on CPU independently of the
embedding backend.

Linux Vulkan needs working vendor drivers and /dev/dri access. CUDA needs an
NVIDIA GPU and NVIDIA Container Toolkit. An unavailable selected GPU produces a
startup error before model setup; explicitly choose CPU to run without acceleration.
Vulkan supports compatible Intel/AMD integrated GPUs as well as discrete GPUs.
The launcher probes `llama-server --list-devices`; set `PI_GPU_DEVICE=Vulkan1`
(or `CUDA1`) if the intended device is not index 0. The selected device must appear
in the probe. `PI_EMBEDDING_DEVICE=cuda` alone does not provision a GPU runtime:
use `PI_ACCELERATOR=cuda` or `vulkan` and the launcher. Bash launchers target a
local Linux Docker Engine; Windows integrated GPUs use the native PowerShell path.

Windows Vulkan/CUDA uses a pinned native llama.cpp service downloaded and started
automatically alongside the application container; it does not require Vulkan
passthrough into Docker. Vendor drivers are prerequisites. The authenticated
service listens on port 8769 so Docker can reach it. Permit access only from
Docker/WSL in Windows Firewall, not public networks. Its key stays in accelerator/
and is never printed. Run `powershell -File stop.ps1` before switching models or
backends, then start again. Linux uses `make platform-stop` before switching.

CPU/model state persists in the model-cache volume. Windows GPU assets persist
in accelerator/. Linux GPU weights share model-cache. `make platform-stop`
keeps caches. On Windows `powershell -File stop.ps1` also stops the kit's native
service. Stop before changing accelerator. Never use `down -v` unless deleting
cached assets intentionally. Physical GPU support depends on the driver/device;
this release's local verification did not have GPU devices or Windows available.

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
can be acquired. Completed weights and active downloads are retained. Q4 setup
removes its temporary file on failed downloads. Q4 has a distinct vector profile;
upgrading from Q8 rebuilds vectors once. Existing kits preserve their configuration
on export: copy the updated launcher/Compose files and deliberately set
`PI_EMBEDDING_MODEL=qwen-gguf` when upgrading.

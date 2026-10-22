# Project Intelligence deployment

Run `bash start.sh` on Linux or `powershell -File start.ps1` on Windows.
Alternatively run `make platform-start` (GNU Make required). Windows uses
Docker Desktop with WSL2 and Linux containers. Docker Compose 2.30+ is required
for the optional CUDA profile; the CPU profile needs Compose 2.20+.

The target repository defaults to the parent directory. Set PI_TARGET_REPO in
`deployment.env` to change it; use forward slashes for Windows paths. The target
must already exist. First startup automatically downloads the selected embedding
model and Docling layout, table and OCR assets. Allow network access and up to
30 minutes. The launcher reports success only after retrieval readiness.

## Models and hardware

Select the model and backend independently in `deployment.env`:

| PI_EMBEDDING_MODEL | PI_ACCELERATOR | Execution |
|---|---|---|
| qwen | cpu | Qwen PyTorch CPU (default) |
| gemma | cpu | Gemma PyTorch CPU, text and images |
| qwen | vulkan or cuda | Qwen GGUF GPU |
| gemma | vulkan or cuda | Gemma GGUF GPU, text and images |

Run the same start command after editing the file. GPU choices automatically
select the corresponding GGUF model; Gemma also downloads its multimodal
projector. CPU operation never requires a discrete GPU or special GPU driver.
To use the identical GGUF model format on CPU, select `qwen-gguf` or
`gemma-gguf` with `PI_ACCELERATOR=cpu`; this starts a CPU sidecar on both OSes.
Changing PyTorch/GGUF profiles rebuilds vectors in a separate namespace.

Gemma's PyTorch model access may require accepting provider terms and exporting
HF_TOKEN in your shell. Never store credentials in deployment files. Audio/video
embedding is not exposed. Docling OCR still runs on CPU independently of the
embedding backend.

Linux Vulkan needs working vendor drivers and /dev/dri access. CUDA needs an
NVIDIA GPU and NVIDIA Container Toolkit. An unavailable selected GPU produces a
startup error; explicitly choose CPU to run without acceleration.

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

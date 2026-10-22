# Design

Use the existing production CPU image on Linux amd64 and Windows Docker Desktop
with Linux containers. Office graphics do not require a driver inside the
container. Use Qwen as the deployment default to avoid gated downloads.

A separate runnable OCI deployment-kit image exports a fixed allowlist of files
into a dedicated directory without overwriting user configuration. It contains
Compose, deployment.env, a small Makefile and Bash/PowerShell launchers. It needs
no Docker socket and no local source checkout. Compose uses a host repository
bind mount, so the kit is an OCI image rather than native Compose publish (whose
documented bind-mount limitations prevent the required portable layout).

The production workflow builds a candidate, starts a real Qwen model against a
synthetic committed repository, checks readiness/query/MCP and restart, then
publishes the same tested image. The kit references its immutable digest.
Mutable branch aliases are updated only for dev, development or main pushes. Model weights live
in a named volume; image upgrades do not remove it. The startup readiness probe
is distinct from process liveness and has a generous first-download budget.

Do not silently relabel CPU as Vulkan. GPU acceleration needs its own backend,
locked dependencies and physical-device evidence. Keep that limitation explicit.

## GPU requirement confirmed 2026-10-22

The operator requires both CPU operation and real Vulkan acceleration. Add the
official Qwen3-Embedding-0.6B GGUF Q8_0 model as `qwen-gguf`, served by pinned
llama.cpp b11515. Its file digest, quantization, tokenizer and role instructions
form a separate embedding identity from PyTorch Qwen. Validate model identity,
response cardinality, finite values and dimensions; never silently substitute
hashing or a different model when the endpoint fails.

Linux uses a pinned official Vulkan/CUDA sidecar and a setup service that
verifies the model SHA-256 before startup. Windows uses pinned native Vulkan or
CUDA binaries, downloaded and checksum-verified by the launcher, because Docker
Desktop does not promise Vulkan passthrough. A generated local bearer key protects
the host runtime. CPU remains the single-container default. Explicit GPU choices
fail when the requested device is unavailable, with CPU as an operator choice.

The operator approved the existing exact 12-coordinate Python dependency review;
that record does not authorize arbitrary future dependency changes. Upstream
runtime/model downloads remain separate artifacts with recorded hashes/licenses.

## Model/backend extension

The kit selects model and backend independently. Native PyTorch CPU remains the
default; GPU choices resolve to matching Gemma/Qwen GGUF aliases. Both GGUF
aliases can also use a CPU sidecar for format-consistent CPU execution. Gemma
uses the official ggml-org conversion of the existing pinned Google revision,
with separately SHA-256-verified Q8_0 model and multimodal projector. Mean pooling
returns 768d; the adapter truncates to 512d and renormalizes. Its profile includes
both asset hashes and runtime version. Qwen remains last-pooled 1024d.

No Python dependency closure change is required. Runtime images and Windows
archives remain the existing pinned llama.cpp release. Tests distinguish real
CPU runtime/model validation from unavailable physical GPU hardware evidence.

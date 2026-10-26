---
id: adr.0029-portable-model-runtime-and-oci-kit
title: Portable model runtimes and digest-bound OCI deployment kit
kind: adr
status: accepted
date: 2026-10-22
summary: Keep native CPU inference in the application and isolate optional GGUF GPU inference behind an authenticated adapter; distribute a matching standalone deployment kit.
sourceRefs:
  - Containerfile
  - distribution/deployment/compose.sh
  - distribution/deployment/compose.ps1
  - pi_platform/adapters/retrieval/llama_cpp_embedding_model.py
  - .github/workflows/publish-oci-container.yml
related:
  - architecture.portable-deployment
  - adr.0026-embedding-profile-identity-and-vector-namespace
maintenance:
  mode: authored
---

# ADR 0029 — Portable model runtimes and OCI deployment kit

## Context

Office PCs need a real CPU embedding default, while compatible integrated and
discrete GPUs need optional Vulkan or CUDA inference. The locked production
Python environment uses CPU PyTorch; it does not provide a Vulkan backend.
Operators need model provisioning and Docling OCR setup in the startup flow,
without installing the development harness or downloading weights manually.

## Decision

Keep Qwen or Gemma PyTorch CPU inference in the application container. Select
model and accelerator independently. Use pinned llama.cpp GGUF runtimes for
optional Vulkan/CUDA: a Linux sidecar, or a native Windows service reachable
from the application container. Explicit GGUF CPU selection uses a CPU sidecar
on both platforms. Gemma includes a pinned multimodal projector; image bytes
reach the encoder. Docling remains on CPU.

Verify model artifacts by SHA-256. Authenticate local embedding HTTP requests,
check runtime model identity, and reject redirects and unavailable explicitly
selected devices. Keep PyTorch and GGUF vector profiles separate. Resolve the
effective model/device before fingerprinting or publishing persisted status.

Publish the tested production image with immutable commit tags and a matching
OCI kit that pins its image digest. The kit contains Compose, non-secret defaults,
product Make targets and Bash/PowerShell launchers. Export preserves existing
operator files. Branch aliases advance only after required workflow gates.
Accept dependency-review exceptions only against the approved exact closure;
retain notices/evidence and leave the default license policy unchanged.

## Alternatives and consequences

A CUDA-only Python image excludes office GPUs and enlarges the default image.
Requiring manual native model installation breaks the first-start requirement.
A single generic vector namespace would mix incompatible model outputs.
The selected design adds a service boundary and, on Windows GPU profiles, a
native process lifecycle and firewall requirement. Startup needs network and
persistent disk capacity for models; image availability alone is insufficient
for offline use. Stop before switching backends. Roll back with a retained
runtime/kit pair and matching configuration; preserve model caches and allow
profile-specific derived indexes to rebuild.

## Evidence and limits

Linux CPU startup/search/restart, Gemma pixel-sensitive image inference, the
12 model/backend configurations and full harness passed. Hardware GPU execution,
Windows execution and remote GHCR publication remain pending. Acceptance of
this architectural decision does not certify those environments. See the
[verification report](../../../docs/PRODUCTION_RECONCILIATION_STATUS.md) and
[deployment architecture](../architecture/portable-deployment.md).

## Amendment — 2026-10-25

Clean external-repository installation showed that full-precision weights and
eager document assets impose avoidable startup cost. The deployment kit now
selects the pinned Qwen Q4_K_M CPU sidecar by default; explicit native model
selection retains single-container execution. This supersedes the prior native
CPU default only for the kit. Document assets load only for PDF inputs.

The Q4 artifact is a checksum-pinned community requantization of the official
Qwen GGUF, with retained Apache-2.0 provenance and a distinct vector identity.
Real CPU inference, Java indexing, search and vector reuse pass on a small clean
fixture. Device preflight and explicit device selection improve GPU diagnostics;
physical GPU and Windows execution remain uncertified.

## Update 2026-10-25

The runtime policy described above is now owned by
`pi_platform/core/inference/` (backend vocabulary, `--list-devices`
probe, pure selection policy, launch-plan builder) and exposed
through the `inference plan` / `doctor` / `status` CLI group.
Three refinements apply: the backend is selected automatically in
`cuda -> vulkan -> cpu` order from probe evidence, an
unavailable or unusable GPU downgrades to the validated CPU
profile instead of failing startup, and the runtime flags are
passed as an explicit argument vector rather than `LLAMA_ARG_*`
environment variables, whose names differ from the flag names and
are silently ignored when wrong. See
[`modules/inference-runtime`](../modules/inference-runtime.md).

---
id: architecture.portable-deployment
title: Portable production deployment and model lifecycle
kind: architecture
status: active
summary: Observed CPU and optional GGUF runtime boundaries, setup, persistence, release flow and verification limits.
sourceRefs:
  - Containerfile
  - distribution/deployment/
  - pi_platform/cli/main.py
  - pi_platform/core/orchestration/repository_indexing.py
  - .github/workflows/publish-oci-container.yml
related:
  - adr.0029-portable-model-runtime-and-oci-kit
  - interfaces.one-command-ux
  - modules.retrieval
maintenance:
  mode: authored
---

# Portable production deployment

The production image is Linux amd64. Windows runs the application through Docker
Desktop with WSL2/Linux containers. The exported kit defaults to EmbeddingGemma 2
Q8_0 plus its pinned multimodal projector, served by llama.cpp. The standalone
application image defaults to `gemma-torch`, because it has no managed sidecar.
The diagnostic core image uses hashing rather than semantic inference.

## Runtime selection and ownership

Linux runs CPU, Vulkan or CUDA inference in a sidecar. Windows GPU inference uses
a native service reachable from Docker; CPU inference stays in the container.
Auto selection probes actual runtime devices and compares successful embeddings
against CPU. Software rasterizers and failed candidates are rejected. Missing
measurements select CPU. Explicit GPU selection still requires usable inference,
but does not require outperforming CPU. CPU threads and GPU free-memory fit margins
come from the inference plan; PDF/OCR processing remains on CPU.

Model and projector downloads are hash-checked and cached separately from target
repository indexes. PDF assets are prepared only when needed. The target owns
canonical knowledge and `.project-intelligence-cache/`. Distinct runtime profiles
isolate vector namespaces. Text and repository/PDF images are supported;
audio/video repository ingestion is not exposed.

## Startup and security

Launchers wait for retrieval readiness, not merely liveness. GPU setup failures
fall back to CPU. The version monitor accepts the identity published by bootstrap
so startup-generated configuration does not immediately invalidate readiness;
subsequent user edits still trigger refresh.

The UI binds to loopback. GGUF HTTP uses a bearer key and checks model identity.
Windows firewall access should be limited to Docker/WSL. Credentials are runtime
inputs, never shipped in the image. Existing exported kit files are preserved;
upgrade explicitly using a separately exported kit and its tested image digest.

## Delivery and evidence

The publication workflow builds and tests PRs without publishing. Pushes to dev,
development and main publish the tested image and a digest-bound deployment kit.
Local tests do not prove that a remote branch alias exists. Physical Windows/CUDA
acceptance and remote publication must be recorded separately from software tests.
The broader portable-OCI change remains active until its acceptance is complete.

See [installation](../../../docs/PRODUCTION_INSTALL.md),
[kit operation](../../../distribution/deployment/README.md), and
[review evidence](../../../docs/RUNTIME_PYTHON_REVIEW.md).

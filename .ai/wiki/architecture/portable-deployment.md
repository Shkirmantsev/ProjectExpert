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
The upgraded managed kit mounts a stdlib child supervisor read-only and exposes
its authenticated controller only inside the Compose network. UI selections
use a stdlib-only Python bundle prepared from the application image in the model
volume, avoiding a system-Python assumption in CUDA/Vulkan runtime images. Choices
persist as explicit ignored operator overrides, apply before indexing and follow
an observable job. On Linux, available `/dev/dri` access is also exposed when
starting on CPU, enabling later UI Vulkan selection. Image changes, CUDA device
provisioning and native Windows service control remain host deployment actions.
Current mode is read from the child controller; a cached deployment profile is
not treated as live device evidence. No Docker socket is mounted.

Optional `PI_UI_TOKEN` protects the product API, separate from the internal
embedding key and optional chat credentials. The default local installation
does not configure this operator-defined password. Public authentication
metadata reveals only whether a token is required, and the UI explains the
empty field when unconfigured. The exported Compose forwards an operator's
private `PI_UI_TOKEN`; matching bearer credentials must be configured in clients.
Windows firewall access should be limited to Docker/WSL. Credentials are runtime
inputs, never shipped in the image. Existing exported kit files are preserved;
upgrade explicitly using a separately exported kit and its tested image digest.

On POSIX, a root-run exporter inherits the project parent's UID/GID for a new or
root-owned kit. Re-export repairs root-owned managed files (including preserved
operator environment files) and generated backups; it retains an explicit existing
non-root kit owner. Repair is bounded to exporter-owned entries, skips link targets
and unrelated files, and does not recursively change target-project ownership.

Application images enable project-owner CLI execution. On POSIX startup as root,
the CLI repairs the private project cache and known HF/XDG model-cache paths,
preserves access to the internal model key, sets a private cache HOME, clears
supplementary groups and drops GID/UID to the non-root project owner before
dispatching writers. Subsequent indexing, UI jobs and CLI writes inherit that
identity. This prevents new root-owned cache entries rather than repeatedly
repairing them after writes. Host/non-root execution is unchanged; source-tree
ownership and external link targets are not recursively modified.

## Help-first commands and the effective address — 2026-10-27

- The exported kit's Makefile is **help-first**: bare `make` and
  `make help` print the command list and change nothing. They need
  neither Docker, nor Python, nor `deployment.env`. Startup is
  explicit: `make platform-start` (or `start.sh` / `start.ps1`).
- The reported address is the *effective* one. The control port is
  resolved the way Compose resolves it: the shell environment
  overrides `deployment.env`, `deployment.env` is read as plain
  text (never executed), and `8765` is the fallback. A failed
  readiness never prints `Ready:` and always returns a nonzero exit
  code.
- Every launcher invocation uses the **complete applicable Compose
  topology**: the production service, the one-shot `model-setup`
  and the `embeddings` sidecar are declared together, also for the
  inference-plan and benchmark helpers. A reduced configuration
  made Compose report the healthy sidecars as orphans. The plan
  before the backend is known uses the provisional CPU overlay and
  still starts only the production service (`--no-deps`).
- Nothing is deleted automatically. The launchers never pass
  `--remove-orphans`; a genuinely unrelated container in the same
  project stays visible and stays running.

## Related

- [`adr.0029-portable-model-runtime-and-oci-kit`](../adr/0029-portable-model-runtime-and-oci-kit.md)
- `distribution/deployment/README.md`

## Delivery and evidence

The publication workflow builds and tests PRs without publishing. Pushes to dev,
development and main publish the tested image and a digest-bound deployment kit.
Publication completes after the production gates; the independent core job can
finish earlier. Branch-tagged kit fetches use `docker run --pull=always` to avoid
local stale tags. Export preserves existing files, so upgrading an installed kit
requires adopting its new digest and checking any `PI_IMAGE` override.
Local tests do not prove that a remote branch alias exists. Physical Windows/CUDA
acceptance and remote publication must be recorded separately from software tests.
The broader portable-OCI change remains active until its acceptance is complete.

See [installation](../../../docs/PRODUCTION_INSTALL.md),
[kit operation](../../../distribution/deployment/README.md), and
[review evidence](../../../docs/RUNTIME_PYTHON_REVIEW.md).

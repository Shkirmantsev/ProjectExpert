# 2026-10-11-one-click-distribution Specification

## Purpose
Make the platform installable as "download → start → open browser" (§58) by
finalising the single application container with a default Q4 model sidecar, documenting the optional
two-container profile and the distribution profile matrix (§45), completing the
launcher duty list for Linux and Windows, and verifying a real launch.

## Requirements

### Requirement: Launcher verifies a container runtime

The launcher MUST verify that a supported container runtime is available and
usable before it starts the platform, and MUST fail with actionable guidance when
it is not.

#### Scenario: missing runtime is reported

Given no supported container runtime is available
When the launcher runs
Then it exits non-zero and states which runtime is missing and how to install it.

### Requirement: Launcher prepares volumes and mounts

The launcher MUST create the required named volumes and mount the target
repository into the container at a documented path before start-up.

#### Scenario: target repository is mounted

Given a target repository path
When the launcher starts the platform
Then the repository is mounted at the documented in-container path.

### Requirement: Launcher waits for readiness

The launcher MUST start the container, wait until the platform reports ready, and
MUST NOT report success before readiness is reached.

#### Scenario: launcher reports only after readiness

Given a platform that becomes ready after a delay
When the launcher runs
Then the launcher waits and reports success only after the readiness signal.

### Requirement: Launcher opens the browser and prints the URL

After readiness, the launcher MUST print the local URL and status, and MUST open
the browser when a browser opener is available. A missing browser opener MUST
degrade to printing the URL only.

#### Scenario: no browser opener available

Given no browser opener is installed
When the launcher reaches readiness
Then it prints the URL and exits successfully without failing.

### Requirement: Single-container default
The platform application SHALL keep backend, REST, UI, runtime store and MCP in
one container. The lightweight deployment kit SHALL additionally start its managed
Q4 model sidecar by default. Explicit native model configurations SHALL retain
single-container execution.

#### Scenario: default profile is one container
- **WHEN** a clean kit starts with default settings
- **THEN** its application and Q4 CPU embedding services start automatically

### Requirement: Optional two-container profile
Isolated model runtimes MAY run as a second service. Native model execution and
optional UI integrations SHALL remain explicitly selectable. A model sidecar SHALL
be required only for the selected GGUF profile, including the lightweight default.

#### Scenario: second container stays optional
- **WHEN** the operator selects native Qwen on CPU
- **THEN** no embedding sidecar is started

### Requirement: Documented distribution profiles

The platform MUST document the profiles `core-headless`, `desktop-lite`,
`desktop-local-ai`, `open-webui` and `enterprise`, and each profile MUST share the
same canonical project data model.

#### Scenario: every documented profile starts

Given each documented profile in turn
When the deployment is started
Then the profile starts successfully against the same canonical data.

### Requirement: Pinned, reproducible image inputs

The base image and every bundled third-party image MUST be referenced by an
immutable digest or an exact version. A mutable tag MUST NOT be used for a
bundled component.

#### Scenario: mutable tag is rejected

Given a deployment manifest referencing a mutable image tag
When the distribution is validated
Then the manifest is rejected with a supply-chain error.

#### Scenario: base image is pinned by digest

Given the image build definition
When the base image is inspected
Then it is referenced by digest.

### Requirement: Health and readiness are distinct

The platform MUST expose a liveness health signal and a separate readiness
signal that reflects whether knowledge hydration completed. Liveness alone MUST
NOT be treated as readiness.

#### Scenario: liveness precedes readiness

Given the platform process is running but hydration is still in progress
When health and readiness are queried
Then health succeeds while readiness reports not ready.

### Requirement: Launch smoke verification

The repository MUST provide launch smoke tests that verify the platform starts,
hydrates a small synthetic project, serves the UI port and reports health. Tests
requiring a container runtime MUST be gated so the default offline test suite
stays deterministic.

#### Scenario: offline suite stays deterministic

Given no container runtime is available
When the default test suite runs
Then the launch smoke tests are skipped and the rest of the suite passes.

#### Scenario: gated smoke run verifies the launch

Given a container runtime is available and the gate is enabled
When the launch smoke tests run
Then they assert startup, hydration of the synthetic project, a served UI port and
a health response.

### Requirement: Launcher parity across platforms

The Linux and Windows launchers MUST implement the same documented duty list, and
the supported Windows entry point MUST be documented together with how any
compiled launcher artefact is produced and licensed.

#### Scenario: duty parity is verified

Given both launchers
When their declared duties are compared
Then the duty sets are equal.

### Requirement: GHCR OCI container pipeline on development merges

The repository MUST provide a GitHub Actions workflow that builds, verifies,
and publishes the platform OCI container image to the GitHub Container Registry
(`ghcr.io`) whenever a feature branch is merged or pushed into the development
branches (`dev` / `development` / `main`), and verifies the container build on pull
requests targeting those branches. The pipeline and the resulting image
MUST include only the product runtime (`pi_platform/`, `distribution/`,
`evals/`, `Containerfile`, `docker-compose.yml`) and MUST NOT embed or depend
on the development harness (`harness.py`, `infra/`, `tools/mcp/`, `.ai/`,
`.agents/`).

#### Scenario: merge to development builds and pushes OCI image

Given a feature branch merge or push to `dev`, `development` or `main`
When the OCI container workflow runs
Then it executes the product verification gates, builds `Containerfile`, and
pushes immutable commit-SHA and development tags to `ghcr.io/<owner>/project-intelligence`.

#### Scenario: container image excludes the development harness

Given the `Containerfile` and `.dockerignore`
When the OCI image is built
Then the image contains `pi_platform/`, `distribution/`, and `evals/`, and
contains no development harness files (`harness.py`, `infra/`, `.ai/`,
`.agents/`, `tools/`).

### Requirement: Standalone container provides all platform capabilities

Starting the published OCI container or `docker compose` against a target
repository MUST automatically hydrate and reconcile the target repository on
startup and expose the complete platform surface (REST UI API, static Control
Plane UI, OpenAI-compatible shim, MCP JSON-RPC / CLI surface, optional A2A
Agent Card and task surface, and CLI subcommands including `eval-retrieval`,
`eval-chunk-size-sweep`, `mcp-serve`, `a2a-serve`, and `package-plugins`)
without requiring any host checkout or development harness tooling.

#### Scenario: standalone container reaches readiness and serves all capabilities

Given a user starts the container or `docker compose` with a target repository mounted at `/repo`
When the container boots
Then it automatically hydrates and reconciles `/repo`, reports `200 OK` on `/health/ready`, and serves the UI, REST API (`/api/v1/*`), MCP endpoint (`/mcp`), and optional A2A routes (`/.well-known/agent-card.json`, `/a2a/v1/tasks:send`).

### Requirement: CPU production startup provisions inference assets
Production startup SHALL obtain the selected pinned embedding model automatically.
It SHALL obtain Docling layout/table/OCR assets on demand for PDF inputs, and SHALL
not download these assets for code-only repositories. Persistent caches SHALL be
reused across restarts.

#### Scenario: Clean CPU startup
- **WHEN** the default kit starts against source code with no PDFs
- **THEN** only its selected embedding weights are downloaded

### Requirement: Lightweight deployment
The deployment kit SHALL default to checksum-pinned Q4 Qwen GGUF on CPU, load PDF assets on demand, include Java parsing in production, and support explicit CUDA or Vulkan device selection with actionable startup diagnostics.

#### Scenario: Clean external repository
- **WHEN** the user starts the platform in a clean external repository
- **THEN** the runtime follows this contract without development-harness prerequisites

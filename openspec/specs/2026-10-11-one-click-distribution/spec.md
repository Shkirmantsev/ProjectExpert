# 2026-10-11-one-click-distribution Specification

## Purpose
Make the platform installable as "download → start → open browser" (§58) by
finalising the single-container default image, documenting the optional
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

The default deployment MUST run backend, REST, UI, runtime store and MCP in one
container. The lightweight UI MUST be served by that same container.

#### Scenario: default profile is one container

Given the default distribution profile
When the platform is started
Then exactly one core container runs and serves the UI.

### Requirement: Optional two-container profile

A second container MUST remain optional and MUST be used only for isolated model
runtime or an optional UI integration. It MUST NOT be required by any default
profile.

#### Scenario: second container stays optional

Given the optional UI or model runtime profile
When it is not selected
Then no second container is started.

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

## MODIFIED Requirements

### Requirement: Single-container default
The platform application SHALL keep backend, REST, UI, runtime store and MCP in
one container. The lightweight deployment kit SHALL additionally start its
managed managed model sidecar by default. Explicit native model configurations
SHALL retain single-container execution.

The default sidecar MUST load the pinned model together with its pinned
multimodal projector, so that the default profile is the full multimodal
profile and not a text-only profile.

#### Scenario: default profile is one container
- **WHEN** a clean kit starts with default settings
- **THEN** its application and managed CPU embedding services start automatically
- **AND** the embedding service reports the multimodal capability

### Requirement: Optional two-container profile
Isolated model runtimes MAY run as a second service. Native model execution and
optional UI integrations SHALL remain explicitly selectable. A model sidecar SHALL
be required only for the selected profile, including the lightweight default.

#### Scenario: second container stays optional
- **WHEN** the operator selects the native binding of the model on CPU
- **THEN** no embedding sidecar is started

### Requirement: Launcher parity across platforms

The Linux and Windows launchers MUST implement the same documented duty list, and
the supported Windows entry point MUST be documented together with how any
compiled launcher artefact is produced and licensed.

The backend selection duty MUST be identical on both platforms: both launchers
MUST discover the available backends automatically, MUST validate the selected
device with the runtime itself, and MUST fall back to the CPU profile when no
GPU candidate validates. Neither launcher MAY require a per-machine manual
backend selection, and a wrong manual selection MUST NOT abort the deployment.

#### Scenario: duty parity is verified

Given both launchers
When their declared duties are compared
Then the duty sets are equal.

#### Scenario: a workstation without a supported GPU starts

Given a Windows or Linux workstation with an office graphics driver, an
integrated GPU, or no GPU
When the operator runs the launcher without changing the backend setting
Then the launcher selects a validated backend automatically
And the application starts
And the selected backend and the rejected candidates are reported

### Requirement: Lightweight deployment
The deployment kit SHALL default to the pinned EmbeddingGemma 2 Q8_0 GGUF
backbone together with the pinned Q8_0 multimodal projector on CPU, load PDF
assets on demand, include Java parsing in production, and support automatic
CPU, CUDA or Vulkan device selection with actionable diagnostics.

#### Scenario: Clean external repository
- **WHEN** the user starts the platform in a clean external repository
- **THEN** the runtime follows this contract without development-harness prerequisites

#### Scenario: default profile is the multimodal model
- **WHEN** a clean kit starts with default settings
- **THEN** the runtime loads the pinned backbone and the pinned projector
- **AND** the embedding service advertises the multimodal capability

## ADDED Requirements

### Requirement: GPU-independent default

The default deployment MUST run real embedding inference on CPU without requiring
CUDA or Vulkan drivers. Documentation MUST distinguish compatibility with hosts
having office graphics from GPU-accelerated inference.

The launcher MUST treat an unavailable or unusable GPU as a downgrade to the
validated CPU profile, not as a startup failure. It MUST NOT require a
per-machine manual backend selection.

#### Scenario: No accelerator available
Given a Linux or Windows host with no supported GPU passthrough
When the default deployment starts
Then the selected real embedding model executes on CPU
And the deployment reports that the CPU profile was selected

#### Scenario: an unusable GPU is a downgrade
Given a host whose selected GPU backend cannot be validated
When the deployment starts
Then the deployment uses the validated CPU profile
And the application starts and serves normally
And the downgrade is reported with the rejected candidates

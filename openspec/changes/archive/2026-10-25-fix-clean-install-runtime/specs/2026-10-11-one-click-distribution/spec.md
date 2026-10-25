## ADDED Requirements

### Requirement: Lightweight deployment
The deployment kit SHALL default to checksum-pinned Q4 Qwen GGUF on CPU, load PDF assets on demand, include Java parsing in production, and support explicit CUDA or Vulkan device selection with actionable startup diagnostics.

#### Scenario: Clean external repository
- **WHEN** the user starts the platform in a clean external repository
- **THEN** the runtime follows this contract without development-harness prerequisites

## MODIFIED Requirements

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

### Requirement: CPU production startup provisions inference assets
Production startup SHALL obtain the selected pinned embedding model automatically.
It SHALL obtain Docling layout/table/OCR assets on demand for PDF inputs, and SHALL
not download these assets for code-only repositories. Persistent caches SHALL be
reused across restarts.

#### Scenario: Clean CPU startup
- **WHEN** the default kit starts against source code with no PDFs
- **THEN** only its selected embedding weights are downloaded

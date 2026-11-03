## ADDED Requirements

### Requirement: Applied embedding selections
The UI SHALL manage supported embedding bindings and execution devices through an observable apply/index job. An explicit UI selection SHALL persist across serving restarts and take precedence over deployment defaults. Unsupported choices SHALL fail actionably without claiming they were applied. Active mode SHALL represent observed runtime state separately from requested Auto; progress and failure SHALL remain visible.

#### Scenario: Managed CPU to available GPU
- **GIVEN** an upgraded managed runtime with a validated exposed GPU
- **WHEN** the operator applies its GPU device in the UI
- **THEN** the child runtime is reconfigured and health-validated before index publication, and the UI displays the observed GPU/Hybrid result

#### Scenario: Model binding switch
- **GIVEN** a supported Gemma binding choice
- **WHEN** the operator applies it
- **THEN** the existing model factory provisions that binding and publishes its validated index without rewriting canonical knowledge

### Requirement: Clear optional API authentication
The UI SHALL state whether an API access token is configured without revealing its value. It SHALL explain that PI_UI_TOKEN is operator-defined, protects ProjectExpert API access, is independent of provider credentials and is unnecessary when authentication is unconfigured.

#### Scenario: No operator token
- **GIVEN** PI_UI_TOKEN is unset
- **WHEN** the page loads
- **THEN** it explains no token is required and does not ask the user to find a nonexistent generated credential

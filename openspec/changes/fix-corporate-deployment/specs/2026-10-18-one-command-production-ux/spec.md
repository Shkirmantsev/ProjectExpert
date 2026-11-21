## ADDED Requirements

### Requirement: verified native host route and inference launch options
The production kit MUST verify a Windows native embedding route on the target container network before application startup. It MUST support custom embedding ports and explicit tokenless inference for the unpublished managed sidecar.

#### Scenario: engine provides native host DNS
- **WHEN** a Windows container engine provides host name resolution
- **THEN** the launcher preserves the engine route and selects only an endpoint that validates the expected model and embedding contract

#### Scenario: private managed sidecar with a custom port
- **WHEN** an operator explicitly selects a non-default port and tokenless managed inference
- **THEN** inference clients, probes and health checks address the selected port and the embedding service publishes no host port

#### Scenario: operator connects an existing Windows server
- **WHEN** an operator selects an existing Windows llama-server at a custom port
- **THEN** the same container-route and embedding checks validate the selected service
- **AND** tokenless connection requires an explicitly selected private listener; wildcard and LAN listeners are rejected
- **AND** the launcher does not take ownership of an externally started process

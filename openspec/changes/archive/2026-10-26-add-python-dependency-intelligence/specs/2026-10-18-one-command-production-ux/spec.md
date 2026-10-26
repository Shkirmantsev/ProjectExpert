## ADDED Requirements

### Requirement: Standalone semantic container default
A production application container without a managed inference sidecar SHALL default to the native EmbeddingGemma 2 binding. The deployment kit SHALL retain its managed GGUF default.

#### Scenario: Standalone startup
- **GIVEN** the production image without an external inference endpoint
- **WHEN** started with its default model settings
- **THEN** it selects gemma-torch and provisions native model assets subject to provider access

## ADDED Requirements

### Requirement: Embedding input capacity across launch paths
The shipped native and managed embedding runtime defaults SHALL provide at least 4096 tokens of context, batch and microbatch capacity with one parallel slot. Capacity SHALL not fall below the known 1049-token project input. CPU, Vulkan and CUDA launch paths SHALL use equivalent capacity defaults.

#### Scenario: Wider project chunk
- **GIVEN** a project embedding input of 1049 tokens
- **WHEN** the runtime uses shipped defaults
- **THEN** it does not reject the input due to a 1024-token batch or microbatch limit

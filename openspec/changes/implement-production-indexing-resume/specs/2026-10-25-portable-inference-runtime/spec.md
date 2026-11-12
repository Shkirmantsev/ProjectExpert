## ADDED Requirements

### Requirement: Measured accelerator comparison without fixed ten-percent gate
Automatic resource comparison MUST NOT reject a usable accelerator solely
because its measured advantage is less than ten percent. Non-finite or
non-positive timings MUST be treated as inconclusive. Stage evidence MUST
retain its workload scope and MUST NOT be reused as a benchmark for a different
stage, model identity or live runtime session.

#### Scenario: modest measured improvement
- **GIVEN** a validated GPU with measured median runtime two percent below CPU
- **WHEN** default automatic selection compares the backends
- **THEN** the former ten-percent threshold does not reject the GPU

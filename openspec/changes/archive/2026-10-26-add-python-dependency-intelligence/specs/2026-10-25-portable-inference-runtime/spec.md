## ADDED Requirements

### Requirement: Measured device consistency
Linux GPU measurement SHALL use the same validated device and memory fit settings as the final inference plan. A successful device enumeration followed by failed startup or invalid embedding output SHALL reject the candidate. Automatic selection SHALL fall back to CPU when required measurements are unavailable.

#### Scenario: Enumerated GPU cannot load the model
- **GIVEN** a runtime reports a GPU
- **WHEN** candidate model startup fails
- **THEN** the launcher selects CPU and does not treat enumeration as successful inference

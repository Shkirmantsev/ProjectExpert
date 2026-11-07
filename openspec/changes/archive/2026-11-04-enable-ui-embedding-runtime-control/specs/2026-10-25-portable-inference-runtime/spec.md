## ADDED Requirements

### Requirement: Bounded managed runtime control
A managed runtime controller SHALL own only the embedding server child, authenticate mutations, validate device identifiers and preserve its fixed model/path/launch constraints. It SHALL expose observed state and available devices. Auto SHALL reuse the accepted measured CPU/GPU policy. It SHALL not require a Docker socket in the application. Failed reconfiguration SHALL restore the previous child when possible and prevent unverified index publication.

#### Scenario: Invalid or unavailable GPU
- **GIVEN** a requested device not available to the controller
- **WHEN** reconfiguration is requested
- **THEN** no arbitrary process is launched, the previous child is retained or restored and an actionable failure is returned

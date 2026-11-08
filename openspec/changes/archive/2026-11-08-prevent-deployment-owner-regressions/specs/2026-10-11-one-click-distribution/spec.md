## ADDED Requirements

### Requirement: Ownership-compatible application startup
Compose application services SHALL prepare project-user execution before CLI writers run. An image lacking that capability SHALL fail before creating target files and explain that its application image or kit must be upgraded. This guard SHALL apply to image overrides and invocation without deployment.env, while supported parameter-free startup SHALL remain available. Published kit verification SHALL resolve its tested matching application image without deployment.env and SHALL verify real cache/Wiki writer ownership.

#### Scenario: Legacy image override
- **GIVEN** a kit configured with an application image lacking ownership preparation
- **WHEN** its application service starts, with or without deployment.env
- **THEN** it fails with an actionable compatibility error before creating target cache or Wiki files

#### Scenario: Supported default image
- **GIVEN** a published kit containing its verified application image pin
- **WHEN** an operator starts it without setting PI_IMAGE manually
- **THEN** the application runs writers as the project owner

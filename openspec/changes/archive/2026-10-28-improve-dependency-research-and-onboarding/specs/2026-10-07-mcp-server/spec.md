# Specification delta

Proposed; not adopted current behavior.

## ADDED Requirements

### Requirement: Dependency research tool surface
MCP SHALL expose schema-described graph, symbol-search, code-read and explicit artifact-acquisition operations backed by shared research logic. Arguments and outputs SHALL enforce project boundaries, budgets and policy. Existing get_dependency Maven arguments SHALL remain valid and return evidence or an explicit unavailable/partial result, never echoed coordinates as proof.

#### Scenario: Tools discovery and execution
- **GIVEN** a bound repository with a known transitive dependency fixture
- **WHEN** a client initializes, lists tools and requests its graph then code
- **THEN** schemas validate and returned records reference actual fixture evidence

#### Scenario: Legacy Maven lookup
- **GIVEN** an existing client using group, artifact and version
- **WHEN** get_dependency is invoked
- **THEN** input compatibility is preserved and the result is evidence-backed or explicitly unavailable

#### Scenario: Isolation and errors
- **GIVEN** a request for another repository or invalid evidence reference
- **WHEN** a research tool is invoked
- **THEN** access fails with a bounded structured error and no source leakage

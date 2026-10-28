# Specification delta

Proposed; not adopted current behavior.

## ADDED Requirements

### Requirement: A2A dependency research dispatch
When inbound A2A research is enabled and authorized, an advertised dependency research task SHALL dispatch to the same application operations as MCP and return research artifacts with equivalent provenance and limits. An acknowledgement alone SHALL NOT count as completed research. Disabled, unsupported, denied and timed-out requests SHALL be distinguishable.

#### Scenario: Transport parity
- **GIVEN** the same actor permissions, repository snapshot and research arguments
- **WHEN** equivalent MCP and A2A research requests run
- **THEN** semantic graph/code evidence and policy outcomes agree

#### Scenario: Disabled research
- **GIVEN** A2A inbound is disabled
- **WHEN** a research task is submitted
- **THEN** it fails explicitly and no research or acquisition occurs

#### Scenario: Unsupported operation
- **GIVEN** an unrecognized research action
- **WHEN** the request is submitted
- **THEN** it returns unsupported instead of a completed acknowledgement

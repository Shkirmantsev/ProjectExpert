## ADDED Requirements

### Requirement: Interoperable transport
The server SHALL provide standard initialize serverInfo.version and complete argument schemas, accept notifications without JSON-RPC replies, and return 405 for unsupported GET streams.

#### Scenario: Clean external repository
- **WHEN** the user starts the platform in a clean external repository
- **THEN** the runtime follows this contract without development-harness prerequisites

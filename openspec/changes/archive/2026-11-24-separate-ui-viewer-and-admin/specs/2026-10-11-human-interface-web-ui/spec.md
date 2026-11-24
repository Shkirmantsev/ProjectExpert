## MODIFIED Requirements

### Requirement: Bearer token authentication

When a UI token is configured, browser search, excerpts, source and Wiki browsing, graph exploration, version and readiness SHALL be available without bearer authentication under viewer policy. Viewer search SHALL use local retrieval and viewer status SHALL omit internal diagnostics. Administrative operations and MCP, OpenAI-compatible and A2A calls SHALL require the matching bearer.

#### Scenario: missing token is rejected

Given a configured UI access token
When a privileged request arrives without a bearer token
Then the server returns HTTP 401 and performs no operation.

#### Scenario: viewer opens the workspace

Given a configured UI access token
When an unauthenticated reader opens the browser
Then search and browsing are available and administrator controls appear only after successful authorization.

### Requirement: Clear optional API authentication
The UI SHALL explain that PI_UI_TOKEN protects administrator actions and integrations, and that the matching token unlocks administrator controls. Browser search and browsing SHALL remain available before unlock.

#### Scenario: No operator token
- **GIVEN** PI_UI_TOKEN is unset
- **WHEN** the page loads
- **THEN** it explains no token is required and does not show a credential form

### Requirement: Local administrator admission

When PI_UI_TOKEN is unset or empty, ordinary users SHALL have administrator access on every configured listening interface without a credential or a special browser launch. Browser-origin checks for mutations, explicit restricted roles and operation-specific approvals SHALL remain effective. A configured token SHALL require a valid bearer for administration regardless of the request's address.

#### Scenario: Remote browser without a configured token

- **GIVEN** an application reachable through a non-loopback address and an unset or empty PI_UI_TOKEN
- **WHEN** an ordinary user opens the service URL and saves settings
- **THEN** the UI omits the token form, the status reports administrator access and the same-origin write succeeds

#### Scenario: Windows forwarded browser

- **GIVEN** a browser reaching the application through a forwarded address and no configured token
- **WHEN** the user opens the service URL
- **THEN** administration is available without a credential or launch-specific URL

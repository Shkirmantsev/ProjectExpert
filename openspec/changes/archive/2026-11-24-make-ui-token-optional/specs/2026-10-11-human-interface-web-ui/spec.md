## MODIFIED Requirements

### Requirement: Local administrator admission

When PI_UI_TOKEN is unset or empty, ordinary users SHALL have administrator access on every configured listening interface without a credential or a special browser launch. Browser-origin checks for mutations, explicit restricted roles and operation-specific approvals SHALL remain effective. A configured token SHALL require a valid bearer regardless of the request's address.

#### Scenario: Remote browser without a configured token

- **GIVEN** an application reachable through a non-loopback address and an unset or empty PI_UI_TOKEN
- **WHEN** an ordinary user opens the service URL and saves settings
- **THEN** the UI omits the token form, the status reports administrator access and the same-origin write succeeds

#### Scenario: Windows forwarded browser

- **GIVEN** a browser reaching the application through a forwarded address and no configured token
- **WHEN** the user opens the service URL
- **THEN** administration is available without a credential or launch-specific URL

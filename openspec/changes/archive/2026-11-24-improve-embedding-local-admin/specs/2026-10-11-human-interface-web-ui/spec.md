## ADDED Requirements

### Requirement: Local administrator admission

The managed local deployment SHALL open a browser with administrator access through an automatically provisioned private credential when the API token is absent. Uncredentialed requests to the managed administrator surface SHALL remain denied regardless of forwarding address or caller role headers.

#### Scenario: Windows forwarded browser

- **GIVEN** Docker operator access and a loopback-published installation with no API token
- **WHEN** the operator opens the UI from the deployment launcher
- **THEN** administrator requests are authorized through the managed credential, subject to same-origin and domain approval checks

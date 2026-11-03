## ADDED Requirements

### Requirement: Optional chat frontend in the exported kit
The exported kit SHALL include an optional open-webui Compose profile bound to loopback by default. It SHALL connect to the internal ProjectExpert OpenAI adapter and have a health probe independent of jq. Plain platform-start SHALL continue to work without a chat model or profile flag.

#### Scenario: Enable chat-shaped retrieval
- **GIVEN** the operator enables the open-webui profile
- **WHEN** the kit starts
- **THEN** the frontend connects to production:8765/v1 and can expose project-intelligence retrieval without an external chat model

### Requirement: Explicit safe kit upgrade
Default export SHALL preserve existing operator files. Explicit upgrade SHALL replace managed templates with backups, preserve deployment.env and unrelated files, and refuse managed symlink replacement before mutation.

#### Scenario: Upgrade an existing installation
- **GIVEN** an installed kit with a custom control port and CPU selection
- **WHEN** the operator explicitly upgrades managed templates
- **THEN** deployment.env retains those settings and changed templates are recoverable from a backup

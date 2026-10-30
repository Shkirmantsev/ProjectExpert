# user-onboarding Specification

## Purpose
Make the product usable from the first command: a container quick start,
a Python fallback, a use-case table, the real addresses of every
interface and a short, honest account of what is supported and what is
not. The capability is about the documentation a new user actually
follows.

## Requirements

### Requirement: Readable product entry point
The root README SHALL explain ProjectExpert in plain language and present a preferred container setup command followed by a separate run command, a Python virtual-environment fallback, a use-case/interface table, capability limits and configuration entry points. Detailed architecture, operations and contributor material SHALL be linked rather than repeated. No proposed capability SHALL be advertised as shipped.

#### Scenario: New container user
- **GIVEN** a supported machine with Docker and an existing target repository
- **WHEN** a reader follows only the quick-start prerequisites and two labelled commands
- **THEN** the correct repository is mounted and the browser URL and readiness check are clear

#### Scenario: Docker unavailable
- **GIVEN** a supported Python host without Docker
- **WHEN** the reader follows the linked venv setup and run instructions
- **THEN** the product starts independently of optional harness integrations; unsupported host restrictions are explicit

### Requirement: Interface and process navigation
User documentation SHALL list UI, REST, MCP, optional A2A and optional Open WebUI with effective URLs, ports, enabling conditions and authentication references. Expanded documentation SHALL contain readable architecture, user workflow and data/knowledge lifecycle diagrams with text equivalents.

#### Scenario: Choose an interface
- **GIVEN** a user wants a browser, coding-agent or chat interface
- **WHEN** they consult the README and linked interface guide
- **THEN** they can identify which service to run and where to connect, including optional service prerequisites

#### Scenario: Diagram unavailable
- **GIVEN** a renderer cannot display Mermaid
- **WHEN** the reader uses the expanded guide
- **THEN** adjacent prose explains the same flow and all navigation links resolve

### Requirement: Pre-run optional chat binding
The exported kit SHALL provide platform-llm-configure, platform-llm-status, platform-llm-test and platform-llm-disable Make commands that work before the serving container runs. Configuration SHALL reuse private server settings without requiring a host Python, chat provider contact or embedding startup. Provider keys SHALL travel through environment/stdin rather than printed command arguments.

#### Scenario: Configure before startup
Given no serving container is running
When an operator runs platform-llm-configure with endpoint, model and explicit context consent
Then a no-dependency one-shot container saves validated chat settings and prints only redacted configuration.

### Requirement: Optional startup chat flag
platform-start SHALL preserve saved configuration by default. LLM=1 SHALL configure/enable chat before starting services; LLM=0 SHALL disable it before starting services. Failed preconfiguration SHALL prevent startup.

#### Scenario: Explicit binding during startup
Given explicit LLM=1 and valid operator settings
When platform-start is invoked
Then configuration completes before Compose up; secrets do not appear in Make output.

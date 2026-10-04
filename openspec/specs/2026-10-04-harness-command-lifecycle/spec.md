# Harness Command Lifecycle Specification

## Purpose

Provide complete portable setup and Wiki workflows with a connectable, owned
background MCP lifecycle while retaining automatic client-managed stdio.

## Requirements

### Requirement: portable operator workflows

The harness SHALL expose core init, init-mcp, Wiki init/index/validation and MCP
run/stop/status/logs/clean through both Make and `python harness.py`. It SHALL
provide donor-compatible harness-* aliases and mcp-run/mcp-stop aliases. Core
Make help and recipes SHALL work without Bash or awk on Linux and Windows.
Wiki initialization SHALL validate and index existing Markdown without overwriting
it. Initialization with MCP SHALL install the local runtime and generate clients.

#### Scenario: preparing the project

- **WHEN** an operator runs init-mcp and wiki-init through either interface
- **THEN** local MCP dependencies, client configuration and the disposable Wiki index are prepared
- **AND** authored Wiki Markdown and existing .env values are preserved.

### Requirement: connectable background MCP

run-mcp SHALL start the project-context MCP with a connectable Streamable HTTP
endpoint bound to localhost. It SHALL succeed only when the owned instance is
ready, be idempotent while ready, and fail for a missing install or port conflict.
Default generated clients SHALL retain stdio; explicit HTTP configuration SHALL
point Claude, OpenCode and Codex at the matching localhost endpoint.

#### Scenario: using a manually started server

- **WHEN** an MCP client connects to the background endpoint after run-mcp succeeds
- **THEN** initialization, tool listing and Wiki search requests succeed.

#### Scenario: port occupied by another server

- **WHEN** another instance occupies the configured port
- **THEN** run-mcp fails without claiming or stopping that instance.

### Requirement: owned lifecycle and non-destructive cleanup

stop-mcp SHALL stop only its supervisor-owned server through an instance-scoped
control request. Status SHALL check readiness without terminating a process.
Logs SHALL expose recent diagnostic output. mcp-clean SHALL refuse active workers
and remove only stopped lifecycle state and logs. Whole-runtime clean SHALL refuse
an active background MCP. Lifecycle actions SHALL preserve client-owned stdio
servers, external MCP servers, source, Wiki, .env and installed runtime dependencies.

#### Scenario: stopping and cleaning

- **WHEN** an operator stops the managed instance and then runs mcp-clean
- **THEN** that instance exits and its state/log files are removed
- **AND** unrelated files and processes remain intact.

#### Scenario: stale state or active cleanup

- **WHEN** state references an exited worker or cleanup is requested during operation
- **THEN** no unrelated PID is signalled
- **AND** active cleanup fails with a stop-first instruction.

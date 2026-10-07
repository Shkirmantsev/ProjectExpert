# Documentation map

[Project home](../README.md) · [Wiki index](../.ai/wiki/INDEX.md) · [Structure and ownership](PROJECT_STRUCTURE.md)

## Setup and daily work

- [Quick start](QUICKSTART.md): initialize, install MCP, and validate.
- [Harness commands and MCP lifecycle](HARNESS_COMMANDS.md): setup, Wiki init
  and manual MCP start/stop.
- [Configuration](CONFIGURATION.md): supported settings and client generation.
- [OpenCode compatibility](OPENCODE_COMPATIBILITY.md): selecting a configuration generation.
- [Engineering conventions](conventions/README.md): task-specific design, implementation, testing, and review defaults.
- [Accepted project state ("actual is")](../openspec/CURRENT.md): all current capability requirements.
- [OpenSpec workflow](../openspec/README.md): artifact dependencies and adoption.
- [Skills](SKILLS.md): routing and reusable procedures.
- [Security](SECURITY.md): credentials and project boundaries.
- [Troubleshooting](TROUBLESHOOTING.md): configuration and service diagnostics.

## Optional infrastructure

These services are disabled by default in `.env`. Enable only what this project
needs, then run `make runtime` to regenerate client configs.

- [Web stack](WEB_STACK.md): SearXNG, Crawl4AI, and Playwright.
- [Hermes native setup](HERMES_NATIVE_SETUP.md): client transports and deployment.
- [Hermes remote instructions](HERMES_REMOTE_AGENT_INSTRUCTION.md): worker operating contract.

## Reference

- [Project structure](PROJECT_STRUCTURE.md): ownership and dependencies of every file family.
- [Third-party skills](THIRD_PARTY_SKILLS.md) and [licenses](../third_party/licenses/skills).
- [Harness framework adoption](../.ai/wiki/project/harness-framework-adoption.md): which framework files are imported and which are excluded.

## Phase handoffs

- [Phase 2 problem statement and resolution](handoff/phase-2-problem-statement.md)
- [Phase 3 follow-up prompt](handoff/phase-3-prompt.md)

- [Phase 6 implementation prompt and readiness](handoff/phase-6-implementation-prompt.md)

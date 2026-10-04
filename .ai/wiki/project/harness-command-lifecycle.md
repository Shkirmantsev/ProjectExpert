---
id: project.harness-command-lifecycle
title: Harness Commands and MCP Lifecycle
kind: project
status: active
summary: Portable setup and Wiki commands, plus connectable localhost MCP lifecycle with process ownership.
sourceRefs:
  - harness.py
  - Makefile
  - scripts/project_mcp.py
  - scripts/configure_clients.py
  - tools/mcp/project-context-mcp/project_context_mcp/server.py
maintenance:
  mode: authored
---

# Harness command lifecycle

[Operator instructions](../../../docs/HARNESS_COMMANDS.md) contain the complete
setup, Wiki and manual MCP workflows. Make is optional; the core Python CLI is
portable on Linux and Windows. Wiki initialization validates and indexes existing
Markdown without replacing it.

The default client transport remains stdio. Manual run-mcp starts a loopback
Streamable HTTP server, with optional HTTP client config pointing at its endpoint.
The supervisor owns the child process and acknowledges instance-scoped stop-file
requests. It never terminates a PID copied from state. Windows readiness uses
native process queries rather than os.kill(pid, 0). Instance/PID health checks
prevent an unrelated listener from satisfying startup readiness. State, logs and
control files remain disposable local evidence under tmp/local/mcp.

The donor's command surface is explicitly adopted with corrected transport and
process ownership. The prior detached stdio implementation was not connectable.
See tests/test_harness_commands.py and the MCP package's tests/test_lifecycle.py
for alias/configuration, real protocol exchanges, duplicates, port conflicts and
stop/cleanup preservation checks. Existing stdio handshake coverage is retained.

Accepted requirements: [command lifecycle](../../../openspec/specs/2026-10-04-harness-command-lifecycle/spec.md).
Verified feature `37307fa`: 100 local full-gate tests and all seven native CI jobs
passed, including full Windows 3.11/3.13 HTTP/stdio and native Make checks.
Windows venv redirectors are bypassed for the supervisor/server so process
handles own the actual Python processes while loading the pinned venv packages.
Development integration uses a local merge and remote push; main remains user-owned.

Supervisor-side failures (including malformed venv configuration and interpreter
launch errors) append the exception and traceback to the lifecycle log before
recording failure. Owned-child cleanup remains in the failure path, including
when diagnostic logging itself fails. `mcp-logs` exposes these diagnostics.
Regression coverage lives in tests/test_harness_commands.py.

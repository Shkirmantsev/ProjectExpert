---
name: harness-project-access
description: Use native remote Hermes project access safely through its configured SSH backend and dedicated main-PC account.
---
# Native Hermes project access
- The remote Hermes profile owns its project tools. `terminal`, `read_file`, `write_file`, `patch`, search, and native media resolution must use its configured SSH backend.
- Every delegated request carries the absolute authorized `PROJECT_ROOT`; establish that repository as the working context before project operations. There is no shared `/workspace` symlink.
- Do not proxy ordinary repository file operations through MCP, HTTP project bridges, session bindings, or attachment relays.
- Do not widen ACLs, use another main-PC account, or inspect unrelated repositories/private user data.
- Repository images are normal project paths for Hermes. Current Hermes vision resolution can read image bytes inside a non-local SSH backend; use native vision tooling and the configured auxiliary vision route when needed.

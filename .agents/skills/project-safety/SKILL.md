---
name: project-safety
description: Enforce the selected project boundary and protect credentials in the reusable multi-agent harness.
---
# Project safety
- Work only in the active project.
- Remote Hermes uses a dedicated unprivileged main-PC user with ACL access to the selected project only; do not widen that access to a home directory or host root.
- Never expose `.env`, generated API keys, provider tokens, Tailscale credentials, browser profiles, or unrelated user files.
- A permission denial is a security boundary, not an invitation to bypass it.

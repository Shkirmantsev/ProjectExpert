# Security model

- Optional local MCP ports bind loopback only.
- Remote Hermes API and Claude MCP sidecar should bind only inside the tailnet and require separate bearer credentials.
- Hermes repository access uses a dedicated unprivileged Linux account plus ACL on the exact `PROJECT_ROOT`, not the owner's normal login.
- Tailscale SSH is recommended to avoid copying project SSH private keys.
- `PROJECT_ROOT=/`, `/home`, an entire user home and other broad system roots are rejected.
- The Claude MCP sidecar has **no filesystem mount/project-file API**; it only controls native Hermes runs.
- The Claude MCP sidecar normalizes caller roots and enforces exact membership in
  `HERMES_ALLOWED_PROJECT_ROOTS` before forwarding a run.
- OpenCode holds direct Hermes Runs API tooling; it does not route Hermes through LiteLLM or the Claude MCP sidecar, and it does not represent Hermes as a normal model provider.
- OpenCode delegation requires resolver-backed run approvals; unattended
  auto-approval is never an accepted compatibility fallback.
- Generated client credentials/config files are gitignored and published
  atomically with mode 0600 where applicable.
- Do not expose LiteLLM, Hermes or MCP endpoints to public/LAN interfaces merely to make the harness work.

The dedicated-user ACL model is simpler than a VM/filesystem sandbox. World-readable operating-system files may remain visible to that Linux account. Use a dedicated VM/container host if strict host isolation is required.

The restricted Hermes account must use `python harness.py check-delegated`; it
must not be granted `.env` access merely to run repository verification.

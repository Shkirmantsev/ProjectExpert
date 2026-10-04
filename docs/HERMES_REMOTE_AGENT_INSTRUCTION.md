# Remote Hermes Agent finalization

This reusable layout intentionally has **two different Hermes ingress paths**:

```text
OpenCode -> project-local `hermes_*` tools -> native Hermes `/v1/runs` API
Claude Code -> dedicated remote Hermes MCP sidecar -> native Hermes /v1/runs
```

They are not unified in this phase because the clients have different integration architecture.

Run:

```bash
make hermes-remote-instructions
```

After `.env` is configured, this renders `.generated/HERMES_REMOTE_SETUP.md` with the exact main-host Tailscale DNS name, project root, remote profile, ports and user names. Give that rendered file to a Hermes/operator session on the remote host.

Before applying it on the remote host, run on the main machine:

```bash
make hermes-host-setup ENABLE_TAILSCALE_SSH=1
make hermes-sidecar-copy
```

The rendered instruction preserves the existing Hermes API server/provider/SOUL/memory, migrates repository access to Hermes' native SSH backend, installs the small Claude-only MCP sidecar, verifies native file/vision behavior, and removes the old project/session/attachment bridges only after native access succeeds.

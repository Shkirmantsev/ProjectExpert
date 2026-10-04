# Hermes Native Claude MCP Sidecar 1.1

A small **Claude Code-only** MCP control sidecar for an existing native Hermes Agent.

```text
Claude Code -> remote MCP :8775 -> native Hermes API on localhost:8642 -> Hermes Agent
OpenCode   -> native Hermes /v1 API directly (no MCP sidecar)
Hermes     -> native SSH backend -> dedicated main-PC project account
```

The sidecar never transports project files. It exposes only run lifecycle operations:

`hermes_run`, `hermes_status`, `hermes_wait`, `hermes_result`, `hermes_steer`, `hermes_approve`, `hermes_cancel`.

Important behavior:

- `HERMES_API_BASE_URL` is the **server root**, normally `http://127.0.0.1:8642`, not `/v1`.
- `hermes_run` deliberately omits a `model` field. Hermes `/v1/runs` treats `model` as a true per-request model override; the sidecar must preserve the configured worker-profile model/provider.
- `hermes_run` accepts only exact normalized paths named by
  `HERMES_ALLOWED_PROJECT_ROOTS`; the allowlist is mandatory server policy.
- New delegations get fresh Hermes session IDs. Pass a previous `session_id` only when you intentionally want continuity.
- `hermes_wait` returns immediately for `waiting_for_approval`; it does not hang until timeout.
- Each upstream request is capped at 30 seconds and a wait request caps it
  further by the remaining caller deadline.
- `hermes_approve` exists for explicit approval resolution and is never invoked automatically.

## Install

```bash
make init
# edit .env: profile path, Tailscale DNS/IP
make import-api-key
make check
make test
make install
make up
make verify
```

The existing native Hermes gateway must already be running and expose its authenticated API on loopback port 8642.

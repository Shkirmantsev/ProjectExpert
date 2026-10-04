# Configuration

Root `.env` is the normal local configuration file. It is created from `.env.example` by `python harness.py init` and must not be committed.

## Portable/core flags

| Variable | Default | Purpose |
|---|---:|---|
| `PROJECT_CONTEXT_MCP_ENABLED` | true | Generate project-context MCP client entries. Install it with `python harness.py mcp-install`. |
| `OPENCODE_CONFIG_GENERATION` | v1 | `v1` = stable/production OpenCode generation; `v2` = OpenCode 2 beta native generation. |

## Optional runtime flags

| Variable | Default | Purpose |
|---|---:|---|
| `LITELLM_ENABLED` | false | Optional local model/protocol gateway. |
| `HERMES_ENABLED` | false | Optional external Hermes delegation/verification; no local Hermes container. |
| `WEB_SEARCH_ENABLED` | false | Optional SearXNG discovery/search. |
| `CRAWL4AI_ENABLED` | false | Optional Crawl4AI render/extract service. |
| `CONTEXT7_MCP_ENABLED` | false | Optional hosted library documentation MCP; no local container. |
| `PLAYWRIGHT_ENABLED` | false | Optional interactive browser MCP. |
| `LITELLM_EXPOSE_ON_TAILSCALE` | false | Optional Tailscale exposure for LiteLLM. |

The default v4 core therefore works without Docker, LiteLLM, Hermes, local models or web services.

## OpenSpec telemetry

`python harness.py init`, `make init`, and `make init-mcp` disable anonymous
OpenSpec telemetry when the optional CLI is installed:

```bash
openspec config set telemetry.enabled false
```

This is an idempotent user-global setting, not a repository setting. If
`openspec` is absent, initialization reports `NOT RUN` and continues. To opt
back in explicitly after initialization:

```bash
openspec config set telemetry.enabled true
```

## OpenCode generation

Keep:

```dotenv
OPENCODE_CONFIG_GENERATION=v1
```

for normal OpenCode V1 work. Use `v2` only when intentionally testing/running `opencode2` beta. Always regenerate with:

```bash
python harness.py client-config
```

See `docs/OPENCODE_COMPATIBILITY.md`.

## Project-context MCP

The server source is versioned under:

```text
tools/mcp/project-context-mcp/
```

Its Python environment is local/disposable:

```text
tmp/local/project-context/venv/
```

Install/update it with:

```bash
python harness.py mcp-install
python harness.py client-config
```

## Optional Hermes variables

- `HERMES_REMOTE_*` — native remote Hermes API used by OpenCode custom run-control tools and verification.
- `HERMES_REMOTE_SIDECAR_PORT` + `HERMES_SIDECAR_TOKEN` — Claude-only Hermes MCP sidecar.
- `HERMES_PROJECT_USER` — unprivileged account on the main project machine.
- `HERMES_PROJECT_DENY_GLOBS` — sensitive paths denied to that account.

Hermes credentials remain in untracked `.env`/generated local material.

## Optional local models

Four generic model slots are retained from v3, but all are disabled by default. Enable only slots actually used by a project.

## Optional Context7 documentation MCP

Set `CONTEXT7_MCP_ENABLED=true` in local `.env` and regenerate with
`python harness.py client-config`. `CONTEXT7_MCP_URL` defaults to
`https://mcp.context7.com/mcp`; `CONTEXT7_MCP_API_KEY` is optional and blank by
default. Only HTTPS URLs without embedded credentials are accepted. The
[Context7 server documentation](https://github.com/upstash/context7) describes
its HTTP endpoint and bearer authentication.

The generator preserves authentication for Claude Code, OpenCode V1/V2 and
Codex using their existing HTTP support. Generated JSON/TOML stays untracked,
is published atomically, and has mode `0600` on POSIX. Windows access follows
local filesystem permissions. Generation and core verification do not connect
to Context7 or install npm packages; service access is optional.

Project-context MCP remains a client-launched stdio server. A detached process
with stdout redirected to a log is not a connection endpoint for clients.


## Project-context MCP transport

`PROJECT_CONTEXT_MCP_TRANSPORT=stdio` keeps the client-managed default.
Set it to `http` to connect all generated clients to the background MCP started
by run-mcp. `PROJECT_CONTEXT_MCP_PORT` defaults to `18883` and accepts 1024–65535.
The server binds only to 127.0.0.1. Regenerate client configs after changing
transport/port; stop and restart the managed server after changing port/root.
See [the command guide](HARNESS_COMMANDS.md) for complete workflows.

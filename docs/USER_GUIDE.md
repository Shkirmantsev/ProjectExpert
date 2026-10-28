# User guide

[Project home](../README.md) · [Architecture](ARCHITECTURE.md) ·
[Dependency research](DEPENDENCY_RESEARCH.md) · [Configuration](CONFIGURATION.md)

This page covers day-to-day use: which interface to open, where to connect,
how requests are authorized and which questions to ask first.

## Choose an interface

| You want | Use | Address | Enabling condition |
|---|---|---|---|
| A browser page | Built-in HTML UI | `http://localhost:8765/` | Default interface; port follows `PI_CONTROL_PORT` |
| Scripts or services | REST API | `http://localhost:8765/api/v1/` | Always on with the UI; optional bearer token when one is configured |
| A coding assistant | MCP over Streamable HTTP | `http://localhost:8765/mcp` | POST only; client must support Streamable HTTP |
| Another agent | Embedded A2A | `/a2a/v1/tasks:send`, `/.well-known/agent-card.json` | `PI_A2A_INBOUND` set to `1`, `true`, `yes` or `on` |
| A standalone A2A process | `python3 -m pi_platform.cli a2a-serve` | Port `8766` by default | Separate process; pass `--target` at the project directory |
| A separate chat frontend | Open WebUI compatibility route | `POST /v1/chat/completions` on the product port | Compatibility route controlled by `PI_OPEN_WEBUI_ADAPTER`; the frontend itself is installed separately |

Port `8765` is the product port (`PI_CONTROL_PORT`). The embedding sidecar uses
an internal service port (`8769`); it is not a browser or chat interface. A code
constant mentioning `8767` is a client-side default only — nothing listens
there by default, so do not publish it as an address.

From another container, `localhost` names *that* container. Use the address the
service is published on, and remember `PI_BIND_HOST` decides which interface
the port is exposed from (loopback by default).

## The built-in web UI

Open `http://localhost:8765/` and start with a concrete question about the
project you mounted, for example:

- “Where is order validation implemented?”
- “Which requirement covers this endpoint?”
- “What changed in the last change set, and which decision justified it?”

The page reports indexing state while it prepares data. Check
`http://localhost:8765/health/ready` for “usable index”; `/health` only says the
process is alive. Findings worth keeping belong in the curated Wiki — see
[dependency research](DEPENDENCY_RESEARCH.md#wiki-reuse) for how a cited answer
is saved and reused.

## REST API

The API is served from the product port under `/api/v1/`. Supported routes:

| Route | Purpose |
|---|---|
| `/api/v1/query` | Ask a question and receive the cited answer |
| `/api/v1/retrieve` | Retrieve context chunks without an answer |
| `/api/v1/graph` | Inspect knowledge-graph entities and relations |
| `/api/v1/wiki` | Read curated Wiki pages |
| `/api/v1/materialize` | Write reviewed changes back into the canonical tree |
| `/api/v1/sources`, `/api/v1/indexing-status`, `/api/v1/knowledge-status`, `/api/v1/project-version` | Source list, index readiness and version state |
| `/api/v1/agent-delegation` | POST a delegation request (task and target) |
| `/api/v1/admin/*`, `/api/v1/wizard` | Operator settings and first-start setup |

**Authentication.** When the operator configures a bearer token, these routes
accept requests only with a matching `Authorization: Bearer` header; with no
token configured they accept requests on the bound interface (loopback by
default). Materialisation additionally needs an operator approval step — see
the [kit guide](../distribution/deployment/README.md).

## MCP for coding assistants

Configure an MCP client against `http://localhost:8765/mcp` using the
Streamable HTTP transport. `GET` returns `405`; `initialize` and `tools/list`
use `POST`. This endpoint is the product's own MCP server — it is not the
harness project-context MCP described in the
[configuration reference](CONFIGURATION.md).

Useful tool groups:

| Group | Tools |
|---|---|
| Search and evidence | `project.search`, `project.retrieve_context`, `project.get_entity`, `project.get_component` |
| Requirements and tracing | `project.get_requirement`, `project.get_spec`, `project.trace_requirement`, `project.find_implementation`, `project.find_references` |
| Dependency research | `project.dependency_tree`, `project.dependency_search`, `project.dependency_read`, `project.dependency_acquire`, `project.get_dependency` |
| Curated Wiki | `project.wiki_list_pages`, `project.wiki_search`, `project.wiki_read_page`, `project.wiki_write_page`, `project.wiki_validate` |
| Operations | `project.refresh_sources`, `project.materialize_knowledge`, `project.describe_capabilities`, `project.get_retrieval_trace` |

A minimal exchange looks like this (no credentials involved):

```bash
curl -s -X POST http://localhost:8765/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"example","version":"0"}}}'
```

Follow it with `tools/list`, then `tools/call` for the tool you need. Argument
shapes for the research tools are documented in
[dependency research](DEPENDENCY_RESEARCH.md).

## A2A for agent-to-agent research

Embedded A2A stays off until `PI_A2A_INBOUND` is `1`, `true`, `yes` or `on`;
while it is off the agent card route returns `404`. A standalone process is
started separately and does not need the embedded surface:

```bash
python3 -m pi_platform.cli a2a-serve --target /absolute/path/to/your-project
```

Research travels in a versioned envelope with an explicit operation:

```json
{"schema_version": 1, "operation": "dependency.tree", "arguments": {"ecosystem": "java"}}
```

Only `dependency.tree`, `dependency.search`, `dependency.read` and
`dependency.acquire` are allowlisted. An unknown operation is rejected — it
never succeeds as an acknowledgement.

## Open WebUI and other chat frontends

`POST /v1/chat/completions` on the product port speaks the OpenAI-compatible
shape so an external frontend can use ProjectExpert as its backend. The route
is controlled by `PI_OPEN_WEBUI_ADAPTER`. It is a compatibility route only:
no chat frontend is bundled, and you install and configure the frontend
yourself against the product address. Keep credentials in your own client
configuration — never in this repository or the exported kit.

## Practical first session

1. Start the product with the [README quick start](../README.md#start-with-docker).
2. Wait for `/health/ready`, then open the UI and ask one specific question.
3. Connect a coding assistant to `/mcp` and repeat the same question there.
4. Save a verified finding with `project.wiki_write_page` (passing the
   `expected_revision` you read) so the next session starts from curated
   knowledge; the page becomes searchable after the next project refresh.
5. When something fails, go to [troubleshooting](TROUBLESHOOTING.md); for
   settings and precedence see [configuration](CONFIGURATION.md).

## Related pages

- [README](../README.md) — quick start, capabilities and limits.
- [Architecture](ARCHITECTURE.md) — how the pieces fit together.
- [Dependency research](DEPENDENCY_RESEARCH.md) — language support and limits.
- [Production install](PRODUCTION_INSTALL.md) — prerequisites, upgrades, rollback.
- [Deployment kit reference](../distribution/deployment/README.md) — exported kit commands.
- [Troubleshooting](TROUBLESHOOTING.md) — readiness, ports and missing evidence.
- [Documentation map](README.md) — contributor and harness material.
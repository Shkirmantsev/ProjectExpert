# Harness setup and MCP commands

[Documentation map](README.md) · [Quick start](QUICKSTART.md)

The Make commands below have the same `python harness.py <command>` interface
on Linux and Windows. Python 3.11+ is required. GNU Make is optional; core recipes
and help no longer require Bash or awk. On Windows Make defaults to `python`,
on Unix to `python3`; override `PYTHON` if your installation uses another name.

## First setup

```sh
make init-mcp
make wiki-init
make check
```

Without Make:

```sh
python harness.py init-mcp
python harness.py wiki-init
python harness.py check
```

`init-mcp` creates or updates .env without overwriting existing values, builds
the Wiki index, synchronizes core skills, installs MCP in the project-local venv,
and generates clients. `init` performs the same setup without installing MCP.
The full check also needs `python -m pip install -r requirements-dev.txt` and the
OpenSpec CLI (CI uses OpenSpec 1.12.0 and Node 22). Core initialization works when
OpenSpec is absent. No Docker or model service is needed for the core workflows.

Wiki init validates existing authored Markdown and builds its disposable SQLite
index. It does not rewrite project knowledge or create guessed business facts.
After editing Wiki pages, use wiki-index and wiki-validate, or wiki-init for both.

## MCP managed by your coding client (default)

With `PROJECT_CONTEXT_MCP_TRANSPORT=stdio`, generated Claude/OpenCode/Codex
configs launch their own MCP process. No manual run-mcp is needed. Use
`make client-config` after installation/settings changes and restart the client.
`python harness.py mcp-stdio` provides a foreground protocol launcher when a
custom client needs one; its stdout contains only MCP traffic.

## Manually started or shared MCP

For a connectable background server, set these non-secret values in .env:

```dotenv
PROJECT_CONTEXT_MCP_TRANSPORT=http
PROJECT_CONTEXT_MCP_PORT=18883
```

Then:

```sh
make client-config
make run-mcp
make mcp-status
```

Or use `python harness.py client-config`, `python harness.py run-mcp` and
`python harness.py mcp-status`. Clients connect to `http://127.0.0.1:18883/mcp`;
restart/reload the client after configuration changes. The listener is loopback
only, intended for local clients on the same machine. Change the port in .env
and regenerate clients if it is occupied. Stop the old instance before changing
its port/root and restarting. Status/stop use the recorded instance, even after
you edit .env. A successful start verifies the actual server's readiness.

| Make or Python command | Result |
|---|---|
| run-mcp / mcp-run | Start the background HTTP MCP; a ready instance is reused. |
| stop-mcp / mcp-stop | Stop only the supervisor-owned background MCP. |
| mcp-status | Report readiness; exit 0 when ready, 1 when stopped/unresponsive. |
| mcp-logs | Print the last 50 diagnostic log lines. |
| mcp-clean | Remove stopped lifecycle state/logs; refuse an active worker. |
| mcp-stdio | Run foreground stdio MCP for a client. |
| wiki-init / init-wiki | Validate canonical Wiki and rebuild its local index. |
| wiki-index / index | Rebuild the index after Markdown changes. |
| wiki-validate | Validate Wiki IDs and links. |

Runtime state, stop requests and logs live in ignored `tmp/local/mcp/`. Stopping
never signals an arbitrary PID from disk, and these commands do not control
client-owned stdio servers or external MCPs. mcp-clean preserves the installed
venv, Wiki and .env. Whole-runtime clean refuses an active background MCP and
otherwise removes the generated runtime/index/venv as before. For missing install,
run mcp-install or init-mcp. On failed start, inspect mcp-logs before retrying.

## Donor-compatible aliases

The donor's `harness-init`, `harness-init-mcp`, `harness-mcp-install`,
`harness-client-config`, `harness-check`, `harness-check-delegated`, `harness-test`,
`harness-wiki-index`, `harness-wiki-validate`, `harness-openspec-check`,
`harness-manifest-generate`, `harness-manifest-check` and `harness-clean` are
available through Make and Python. They delegate to this harness's existing core
commands. `make help` and `python harness.py --help` expose the command inventory.
Product Maven, certificate and application-service commands from the donor remain
outside this reusable harness.

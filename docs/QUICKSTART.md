# Quick start

## 1. Put the harness in the project root

The root should contain `AGENTS.md`, `harness.py`, `.ai/`, `openspec/`, `.agents/`, `tools/`, `scripts/` and your normal product files.

## 2. Initialize

Portable command:

```bash
python harness.py init
```

With Make:

```bash
make init
```

This creates `.env`, builds a disposable local Wiki index and generates client
configuration. If the optional OpenSpec CLI is available, initialization also
runs `openspec config set telemetry.enabled false`. The OpenSpec setting is
user-global; when the CLI is absent, core initialization continues normally.

## 3. Install project-context MCP

```bash
python harness.py mcp-install
python harness.py client-config
```

The virtual environment is deliberately installed under `tmp/local/project-context/venv/` and is ignored by Git.

For one setup command, use `python harness.py init-mcp` or `make init-mcp`.

By default your coding client starts MCP automatically over stdio. For manual
background operation, select `PROJECT_CONTEXT_MCP_TRANSPORT=http` in .env,
regenerate with `python harness.py client-config`, then use
`python harness.py run-mcp` (or `make run-mcp`). See the
[complete command guide](HARNESS_COMMANDS.md) for status, logs, stop and cleanup.

## 4. Validate

```bash
python harness.py check
```

A successful core setup does not require Docker, Hermes, LiteLLM or a local model.

## 5. Describe your project incrementally

Update:

```text
.ai/wiki/architecture/system-overview.md
.ai/wiki/project/project-map.md
.ai/wiki/glossary/domain.md
```

Then:

```bash
python harness.py wiki-init
```

Do not write a huge Wiki upfront. Add durable knowledge around active work.

## 6. Work on behavioral changes

If OpenSpec is appropriate, create/use a change under `openspec/changes/<change-id>/` and follow:

```text
proposal -> specs -> design -> context-impact -> tasks
```

Run:

```bash
python harness.py openspec-check
```

If the OpenSpec CLI is installed, the command also runs its schema validator.

## 7. Select coding client

You may use Claude Code, Codex, OpenCode V1, or optionally OpenCode V2 beta. They share `AGENTS.md` and the same project-context MCP.

### OpenCode production/stable generation

`.env`:

```dotenv
OPENCODE_CONFIG_GENERATION=v1
```

### OpenCode 2 beta

`.env`:

```dotenv
OPENCODE_CONFIG_GENERATION=v2
```

Regenerate after switching:

```bash
python harness.py client-config
```

## 8. Enable optional infrastructure only if needed

Edit `.env`, enable required flags, then on Make-capable hosts:

```bash
make plan
make up
make verify
```


## Full test dependencies

Install the pinned harness configuration/test dependency before running the full
gate or repository unit tests:

```bash
python -m pip install -r requirements-dev.txt
```

GitHub CI installs this dependency on both Linux and Windows. The optional
project-context MCP package has its own dependencies, installed by
`python harness.py mcp-install`. POSIX ACL host setup remains a host-specific
Hermes adapter and reports that requirement explicitly on Windows.


The portable core is required to work on Linux and Windows. CI runs unit tests on
both systems with Python 3.11 and 3.13, plus full Linux and Windows gates with
installed project-context MCP and strict OpenSpec validation. Windows full gates
include a real stdio MCP handshake; optional Docker/Compose and POSIX ACL setup
remain separate host integrations. Use `python harness.py` commands in Windows
PowerShell rather than requiring a POSIX shell or GNU Make.

The generic donor line-ending policy is adopted in `.gitattributes`: text
checkouts use LF on both systems, while Git detects binary files automatically.
This preserves artifact-manifest byte hashes on Windows without importing
business-specific file rules.

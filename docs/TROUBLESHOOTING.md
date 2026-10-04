# Troubleshooting

## Hermes answers but cannot read the repository

1. Run `make hermes-host-setup` on the main PC.
2. From the remote host: `tailscale ping <MAIN_TAILSCALE_HOST>`.
3. Test the same non-interactive mode Hermes uses:
   `ssh -o BatchMode=yes hermes-worker@<MAIN_TAILSCALE_HOST> 'cd <PROJECT_ROOT> && pwd && ls -la'`.
4. Confirm the worker profile has `terminal.backend: ssh`, `cwd: "~"`, and no stale `harness_project` dependency.
5. If manual SSH works but BatchMode fails, inspect the Tailscale SSH policy for an interactive `check` rule.
6. Run `VERIFY_REMOTE_INFERENCE=1 make verify` only after transport works.

## Claude can reach Hermes but delegation fails

Claude uses the **remote sidecar**, not a local container. Check:

```bash
make hermes-check
```

On the remote host:

```bash
systemctl --user status hermes-worker-mcp.service --no-pager
```

Ensure `HERMES_SIDECAR_TOKEN` matches the main `.env` and the sidecar can reach `127.0.0.1:8642 (server root; the sidecar adds `/v1/...` paths itself)` with the existing native Hermes API key.

## OpenCode Hermes fails while Claude works

OpenCode does not use the MCP sidecar. Check native Hermes `/health`, `/v1/models`, `HERMES_REMOTE_API_KEY`, then run `make client-config` and confirm `.opencode/tools/hermes.js` plus `.generated/opencode-hermes-runtime.json` exist. `opencode.json` should **not** contain a `hermes-remote` model provider.

## Repository image cannot be analyzed

Confirm Hermes >=0.20.5 and native SSH project access first. Repository images should be passed as repository paths to Hermes native vision tooling. For a text-only main model, verify a working `auxiliary.vision` configuration.

## PDF/document cannot be parsed

Confirm the file is inside `PROJECT_ROOT` and required project-side CLI support is installed (for example `poppler-utils` for `pdftotext`). External files can be staged with `make hermes-import FILE=...`.

## `make down` leaves something running

`make down` controls only local Compose services and always uses all profiles. Remote Hermes and its remote MCP sidecar are intentionally managed by their own remote `systemd --user` services, not local Docker Compose.

## OpenCode `@generated-hermes` / model-provider delegation fails validation

Revision 3.2 removes that path. Hermes is a full remote agent, so OpenCode must not wrap it as a normal OpenAI-compatible model/subagent. Run:

```bash
make client-config
```

Then restart OpenCode. The project should contain `.opencode/tools/hermes.js`, and `opencode.json` should not contain a `hermes-remote` provider. Ask the normal main model (for example MiniMax):

```text
Delegate repository analysis to Hermes and use its result.
```

The model should call `hermes_delegate`, which starts `POST /v1/runs`; if the run outlives the first wait window it must reuse the returned `run_id` with `hermes_wait`/`hermes_status`/`hermes_result` rather than start a duplicate run.

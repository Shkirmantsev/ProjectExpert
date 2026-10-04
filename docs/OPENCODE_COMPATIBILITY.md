# OpenCode compatibility policy

## Default

`OPENCODE_CONFIG_GENERATION=v1`

V1 is the harness default because OpenCode 2 is currently beta and has intentionally breaking configuration/plugin/server changes.

The V1 generator uses the production documentation schema:

- `provider`
- `permission`
- MCP server names directly under `mcp`
- `enabled` on MCP entries

## Optional V2 beta

Set:

```dotenv
OPENCODE_CONFIG_GENERATION=v2
```

Then run:

```bash
python harness.py client-config
```

Native V2 generation uses:

- `providers`
- `package` + `settings`
- ordered `permissions` rules
- MCP entries under `mcp.servers`
- `disabled` instead of V1 `enabled`

The two formats are generated independently. The harness never creates a mixed V1/V2 configuration.

## Side-by-side use

OpenCode's V2 documentation states that the beta uses the `opencode2` binary and does not replace the V1 `opencode` binary. To test both against one repository:

1. keep V1 selected for normal work;
2. set V2 in `.env`, regenerate and test with `opencode2`;
3. switch back to V1 and regenerate before using `opencode` again.

Because both generations use the same project config path, do not assume one generated file is simultaneously native to both generations.

## ProjectExpert V1 routing scaffold

The installed routing scaffold uses the root `opencode.json` with V1
`provider`, `permission.bash`, `snapshot`, `autoupdate`, and model `options`
and variant maps. Existing harness provider, MCP entries, and credential-read
restrictions are retained. `/route` uses `subtask: false` and selects the
`orchestrator`, which inherits the current session model; select the directly
connected MiniMax M3 through `/models` first.

The three OpenRouter workers are `mimo-flash`, `deepseek-verify`, and `mimo-pro`.
The V1 custom tool is `.opencode/tools/jev_decide.ts`, using
`@opencode-ai/plugin/tool`. It reads only the OpenRouter API credential from
`${XDG_DATA_HOME:-~/.local/share}/opencode/auth.json` in memory and sends a
bounded routing envelope. Connect OpenRouter through `/connect`; no key belongs
in project configuration.

If V1 reports unsupported `permissions` at `.opencode/opencode.json`, move
the stale V2 config and `.opencode/plugins/jev-routing` outside `.opencode`.
The repair backups are under `tmp/local/opencode-v1-backup/`. Disabled copies
there are historical inputs, not active configuration. OpenCode merges config
sources, so a valid root config cannot hide an invalid nested config.

`python harness.py client-config` rewrites the root config from harness settings.
After regeneration, reapply the local V1 scaffold settings by merging its
`provider` and `permission` maps into the generated config and retaining the
generated MCP entries and read restrictions. The scaffold source is
`tmp/local/scaffold_to_install/opencode-v1-m3-openrouter-jev-clean/`.

Validate with `opencode debug config` before starting a session. See the
[OpenCode configuration documentation](https://opencode.ai/docs/config/)
for configuration merge order.

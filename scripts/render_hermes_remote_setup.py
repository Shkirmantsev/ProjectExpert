#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from common import ROOT, parse_env, project_root

def main():
    e = parse_env()
    root = project_root(e).resolve()
    main_host = e.get("MAIN_TAILSCALE_HOST", "CHANGE_ME_MAIN_TAILSCALE_DNS")
    remote_host = e.get("HERMES_REMOTE_HOST", "CHANGE_ME_REMOTE_TAILSCALE_DNS")
    project_user = e.get("HERMES_PROJECT_USER", "hermes-worker")
    profile = e.get("HERMES_REMOTE_PROFILE", "hermes-tailscale-worker")
    remote_user = e.get("HERMES_REMOTE_OS_USER", "hermes")
    runtime_user = e.get("HERMES_REMOTE_RUNTIME_USER", "hermes")
    runtime_home = e.get("HERMES_REMOTE_RUNTIME_HOME", "/srv/ai/hermes")
    staging_dir = e.get("HERMES_REMOTE_STAGING_DIR", "/var/tmp/harness-hermes-worker-mcp")
    api_port = e.get("HERMES_REMOTE_OPENAI_PORT", "8642")
    sidecar_port = e.get("HERMES_REMOTE_SIDECAR_PORT", "8775")
    minv = e.get("HERMES_MIN_VERSION", "0.20.5")
    model = e.get("HERMES_REMOTE_MODEL", "hermes-tailscale-worker")
    text = f'''# Finalize native `{profile}` + Claude Code MCP sidecar

> Execution instruction for the Hermes/operator on the **remote Hermes host** `{remote_host}`.
>
> Target main/project host: `{main_host}`
> Current project used for the smoke test: `{root}`
> Dedicated main-host account: `{project_user}`
> Remote SSH/copy account: `{remote_user}`
> Hermes runtime account/home: `{runtime_user}` / `{runtime_home}`

## Goal

Preserve one native Hermes Agent and expose it through **two deliberately different ingress paths**:

```text
OpenCode on main PC
    └── project-local hermes_* tools ──> native Hermes /v1/runs :{api_port}

Claude Code on main PC
    └── dedicated MCP ──> hermes-worker-mcp :{sidecar_port}
                              └── native Hermes /v1/runs on 127.0.0.1:{api_port}

Hermes repository tools
    └── native SSH backend ──> {project_user}@{main_host}
                                  └── ACL-limited project path(s)
```

Do **not** turn these into one universal client interface in this phase. The MCP sidecar exists specifically for Claude Code. OpenCode must remain a direct native Hermes Runs-API client through project-local custom tools.

The MCP sidecar is control-plane only. It must never proxy repository files, maintain a project binding database, or become a second Hermes runtime.

## Safety / execution context

This runbook modifies the remote host. Perform host-local phases from a Hermes profile/session whose terminal still executes **locally on this remote host**, or from the `{runtime_user}` shell. `HERMES_REMOTE_OS_USER={remote_user}` is only the SSH/copy account used by the main PC and may be different from the Hermes runtime user. If `{profile}` already has `terminal.backend=ssh`, do not rely on that worker's terminal tool to administer its own remote host; use a local/admin Hermes profile for the host-local setup.

Never print `.env`, `auth.json`, OAuth tokens, `API_SERVER_KEY`, or the new sidecar token. Back up before editing. Do not alter the default/main Hermes profile, Telegram routing, memory framework, unrelated skills, or unrelated MCP servers.

---

## Phase 1 — inspect and back up

Run/safely inspect:

```bash
hermes --version
hermes profile show {profile}
systemctl --user status {profile}-gateway.service --no-pager || true
```

Resolve the real profile path from `hermes profile show {profile}` as `WORKER_PROFILE_HOME`. Do not guess it if Hermes reports another location.

Create a timestamped backup:

```bash
BACKUP="{runtime_home}/.local/state/hermes-native-finalize/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
chmod 700 "$BACKUP"
cp -a "$WORKER_PROFILE_HOME/config.yaml" "$BACKUP/config.yaml.before"
cp -a "$WORKER_PROFILE_HOME/.env" "$BACKUP/.env.before"
cp -a "$WORKER_PROFILE_HOME/SOUL.md" "$BACKUP/SOUL.md.before" 2>/dev/null || true
```

Record the gateway unit path and current ExecStart/Environment values **without printing secret values**.

---

## Phase 2 — require current Hermes native capabilities

Target Hermes version: **>= {minv}**. Current releases in this architecture need the native API `/v1/runs`, inline image handling, and SSH-backed media path resolution.

If older than `{minv}`:

```bash
hermes update
hermes --version
hermes doctor
```

Before enabling OpenCode delegation, the worker source must include the
resolver-scoped compatibility fix for `/v1/runs`. On Hermes revision
`4f22543509d1b91dc45bcb369447126c5eb14fb7`, apply the harness patch from the
main project checkout; never set `approvals.unattended_mode: approve`:

```bash
python scripts/apply_hermes_approval_patch.py --source /path/to/hermes-agent --check
python scripts/apply_hermes_approval_patch.py --source /path/to/hermes-agent
```

If update changes the executable/venv path used by `{profile}-gateway.service`, fix only that unit's ExecStart after confirming the new executable. Do not blindly rewrite other gateway units.

---

## Phase 3 — preserve the existing native API server

The existing Hermes API is already the correct OpenCode Runs-API ingress. Preserve:

- profile `{profile}`;
- existing provider/model/OAuth/subscription configuration;
- existing `API_SERVER_KEY` value;
- existing API host/Tailscale-only exposure policy;
- port `{api_port}`;
- SOUL, memory and skills;
- existing `{profile}-gateway.service` supervision.

Verify:

```bash
curl --fail http://127.0.0.1:{api_port}/health
```

Then authenticated `/v1/models` using the existing key, but do not echo the key.

Do **not** put Hermes behind LiteLLM for OpenCode in this design.

---

## Phase 4 — convert project access to native SSH without a project bridge

Merge only these keys into `$WORKER_PROFILE_HOME/config.yaml`:

```yaml
terminal:
  backend: ssh
  cwd: "~"
  timeout: 900
  persistent_shell: true
```

Why `cwd: "~"`: this profile is reusable across projects. Each Claude dispatcher/OpenCode custom-tool delegation supplies the concrete absolute repository root, so there is no global `/workspace` symlink and no per-project remote profile.

Keep Hermes' native `terminal`, `file`, `vision`, `skills`, `memory`, and normal delegation tools enabled. Do not disable file/vision just because the backend is remote.

In the worker profile `.env`, set/replace only the SSH runtime values:

```dotenv
TERMINAL_ENV=ssh
TERMINAL_SSH_HOST={main_host}
TERMINAL_SSH_USER={project_user}
TERMINAL_SSH_PORT={e.get('HERMES_SSH_PORT','22')}
TERMINAL_SSH_PERSISTENT=true
```

### Tailscale SSH / no keypair target

The final target does not require `TERMINAL_SSH_KEY`. First verify the main host has Tailscale SSH enabled and the tailnet SSH policy permits this remote node to connect as `{project_user}` **without an interactive check**.

Hermes' SSH backend uses `BatchMode=yes`, therefore a policy that requires interactive re-authentication can fail even though manual SSH appears to work.

Test from the remote host:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 {project_user}@{main_host} \
  'cd {root} && pwd && test -r . && test -w . && echo PROJECT_ACCESS_OK'
```

Only after this passes:

1. remove `TERMINAL_SSH_KEY` from the worker profile `.env` if it belonged only to the old harness;
2. archive rather than immediately destroy the old dedicated keypair;
3. remove the obsolete `/workspace` assumption from the worker config.

If Tailscale SSH fails, stop and report the policy/host-side problem. Do **not** expose SSH publicly and do not silently create another privileged user/key as fallback.

---

## Phase 5 — prove native file operations before removing old bridges

Use the native Hermes API to start a `/v1/runs` smoke test with instructions that explicitly set repository root `{root}`. The agent must itself:

1. `cd {root}` and report `pwd`;
2. list the root;
3. read a harmless text/Markdown file;
4. create `{root}/.harness/hermes-native-smoke.txt`;
5. read it back;
6. delete it.

All operations must appear as Hermes native terminal/file tool activity. There must be no `harness_project`, project binding DB, project relay, attachment relay, or project-file MCP involved.

If this phase fails, restore from the backup and do not remove the old fallback yet.

---

## Phase 6 — install the dedicated Claude Code MCP sidecar

The main harness contains the sidecar source under:

```text
remote/hermes-worker-mcp/
```

The main-PC operator can transfer it without secrets using:

```bash
make hermes-sidecar-copy
```

Expected neutral staging location:

```text
{staging_dir}/
```

`make hermes-sidecar-copy` deliberately stages outside the SSH/copy user's home so the Hermes runtime user can read the source even when `{remote_user}` != `{runtime_user}`.

From a **host-local** shell/session as the Hermes runtime user on the remote machine:

```bash
SIDECAR_DIR="{runtime_home}/.local/share/hermes-worker-mcp"
mkdir -p "$SIDECAR_DIR"
rsync -rlt --delete --exclude=.env --exclude=.venv \
  "{staging_dir}/" "$SIDECAR_DIR/"
chmod -R u+rwX,go-rwx "$SIDECAR_DIR"
cd "$SIDECAR_DIR"
make init
```

Now populate the sidecar `.env` locally without printing secrets:

- `SIDECAR_TAILSCALE_HOST` = this remote node's MagicDNS/FQDN;
- `SIDECAR_TAILSCALE_IP` = this remote node's Tailscale IPv4;
- `SIDECAR_PORT={sidecar_port}`;
- `HERMES_API_BASE_URL=http://127.0.0.1:{api_port}` (**server root, no `/v1` suffix**);
- `HERMES_API_KEY` = the **existing** worker profile `API_SERVER_KEY` value;
- `HERMES_ALLOWED_PROJECT_ROOTS={root}`;
- `HERMES_SIDECAR_TOKEN` = generated by `bootstrap_env.py` and kept only in the sidecar `.env` plus the main harness `.env` handoff.

Set `HERMES_PROFILE_HOME` in the sidecar `.env` to the exact existing worker profile path, then import the existing API key without printing it:

```bash
make import-api-key
make check
make test
```

The sidecar `.env` must remain mode `0600`.

The sidecar must expose only:

```text
hermes_run(project_root, task, session_id?)
hermes_status(run_id)
hermes_wait(run_id, ...)
hermes_result(run_id)
hermes_steer(run_id, text)
hermes_approve(run_id, choice, resolve_all?)
hermes_cancel(run_id)
```

It must call the existing native Hermes `/v1/runs` API and must NOT send the public profile name as a `/v1/runs` `model` override; omitting the model keeps the profile's configured provider/model authoritative. A run without an explicit `session_id` must create a fresh Hermes session; intentional continuation reuses the returned `session_id`. `hermes_wait` must return when Hermes enters `waiting_for_approval`, and `hermes_approve` may be called only after explicit parent/user authorization. It must not contain a binding store, project relay, skills-upload endpoint, filesystem mount, file upload endpoint, TUI-gateway subprocess, or another Hermes runtime.

Install and start its user service:

```bash
make install
make up
make status
make verify
```

The sidecar must bind only to its Tailscale IP on port `{sidecar_port}`.

Verify its authenticated health endpoint using the sidecar bearer token without printing it. Unauthenticated `/healthz` must return `401`.

---

## Phase 7 — vision and non-text files

Current Hermes supports repository images without a custom file relay:

- the OpenAI API accepts inline `image_url` / `input_image` content;
- the native image resolver can resolve local image paths through a non-local SSH backend and read the bytes inside that backend;
- a text-only main model may use the configured `auxiliary.vision` route.

Verify the worker's `auxiliary.vision` configuration. Do not invent API credentials. If no working auxiliary/native vision model exists, report `VISION NOT CONFIGURED` rather than pretending success.

If the current project contains a safe image, ask Hermes to analyze it **by repository path** using native vision tooling. If no image exists, report the image-path test as `NOT RUN`.

PDFs, archives, code, Markdown, JSON and similar files remain ordinary repository files accessed through native SSH. Use Hermes skills/CLI tools appropriate for the type; do not add a generic attachment server.

---

## Phase 8 — remove obsolete worker-specific bridge components

Only after native SSH + file smoke tests pass, remove or disable obsolete harness-only pieces if present:

- `harness_project` MCP/project bridge;
- session/project binding DB/relay;
- old attachment relay;
- old project-specific `/workspace` symlink assumptions;
- old dedicated SSH key references after Tailscale SSH has passed.

Do **not** remove unrelated MCP servers, skills, memory, provider credentials, or other profiles.

---

## Phase 9 — final client contract

Confirm the intended split:

```text
OpenCode main model
  -> project-local hermes_delegate/status/wait/result/steer/approve/cancel
  -> http://{remote_host}:{api_port}/v1/runs
  -> native Hermes Agent + its native tools

Claude Code
  -> http://{remote_host}:{sidecar_port}/mcp
  -> dedicated MCP sidecar
  -> native Hermes /v1/runs
  -> native Hermes Agent + its native tools
```

Codex is **not** given a Hermes transport in this phase.

---

## Required final report

Return a sanitized report containing:

1. Hermes version;
2. worker profile path/name;
3. backup path;
4. exact config keys changed (not secret values);
5. native API health/models PASS/FAIL;
6. Tailscale SSH BatchMode test PASS/FAIL;
7. native project read/write/delete smoke PASS/FAIL;
8. sidecar service + authenticated MCP health PASS/FAIL;
9. vision configuration and image-path test PASS/FAIL/NOT RUN;
10. obsolete bridge components removed/retained;
11. anything NOT RUN and why;
12. rollback commands.

Do not declare completion if project file access or the Claude sidecar has not actually passed its runtime checks.
'''
    out = ROOT / ".generated/HERMES_REMOTE_SETUP.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(out)

if __name__ == "__main__":
    main()

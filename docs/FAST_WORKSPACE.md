# Managed fast workspace

Managed workspace mode keeps source scans and derived indexes in Linux Docker
volumes while canonical `project-knowledge/` remains directly writable on the host.
It is optional: `PI_WORKSPACE_MODE=auto` currently selects `bind`, as does explicit
`bind`. Existing CPU, CUDA, Vulkan, Windows native inference, model-cache, endpoint
and accelerator selection settings retain their existing behavior.

This guide describes the implementation of the active
[managed workspace change](../openspec/changes/add-managed-fast-workspace/design.md),
not an assertion that its platform acceptance is complete. See the
[implementation plan](superpowers/plans/2026-11-10-managed-fast-workspace.md),
[architecture decision](../.ai/wiki/adr/0032-managed-fast-workspace.md), and
[deployment instructions](PRODUCTION_INSTALL.md).

## Clean installation

Build or obtain a matching application image and deployment kit from this change.
Old images lack the importer/checkpoint modules; old exported kits lack the native
helpers and overlay. Restarting an old installation does not install these changes.
No existing installation is modified by this implementation.

The `Containerfile` deployment-kit target cross-builds standard-library Go helpers
using Go 1.27.4 and includes Linux amd64 and Windows amd64 binaries plus
`workspace-agent-SHA256SUMS`. Hosts need Docker CLI/Compose and the platform shell;
they need no Go or Python installation. The compiler download is pinned by version and SHA-256; no signed
helper release or code-signing validation is claimed. A source-only template export
without built helpers cannot launch managed mode.

In the exported kit's `deployment.env`, set:

```dotenv
PI_TARGET_REPO=/absolute/path/to/project
PI_WORKSPACE_MODE=volume
```

On Windows use the corresponding absolute host path. Relative `PI_TARGET_REPO`
paths resolve from the kit directory. Keep the kit and repository on local storage;
the helper rejects remote Docker endpoints and pins project identity to the local
Docker context/endpoint. Changing that identity requires a deliberate preparation
for the selected project; never copy generated workspace configuration between kits.

Run `bash start.sh` or `./start.ps1` from the kit. The launcher verifies its helper
checksum, prepares storage, checks image compatibility and canonical host write
access, and completes the first verified source import before starting the app.
`up`, `run` and `restart` prepare/synchronize before execution; `up` and `restart`
also start supervision. Read-only Compose commands do not initialize storage.
They still require the existing valid managed configuration/context.

Every applicable Compose invocation appends the managed overlay and reads
`deployment.env` followed by generated `workspace.env`. Treat dotenv as data, never
source it into a shell. Preserve `workspace.env` and `workspace-agent.json` as local
kit state. The source volume is read-only to production, the nested runtime volume
is writable, and only canonical knowledge is bound writable from the host. Wiki atomic writes
sync file contents and the Linux directory entry before returning success; host
power-loss behavior still requires platform acceptance.

## Exclusions and synchronization

Add a `.projectexpert-workspaceignore` file at the host repository root:

```text
# One pattern per line; folder and simple glob patterns
database-dumps/
docker-archives/
*.dump
*.sql.gz
*.tar
*.tar.gz
*.iso
fixtures/archive-*.zip
```

Patterns use `/` separators, match a relative path or a basename, and support
simple `*`, `?` and character-class globs. A trailing `/` excludes a folder.
Recursive `**`, negation (`!`), backslashes, `..` and colon patterns are rejected.
This is a separate policy from Git ignore. Blank lines and comment lines are ignored.
`PI_WORKSPACE_EXCLUDE` supplies additional comma/newline-separated patterns through
the process environment or `deployment.env`. `PI_WORKSPACE_MAX_FILE_BYTES` defaults
to 1 GiB; larger files are skipped before opening/hashing. Raising it does not
remove the overall source/import size bound of 20 GiB.

Built-in exclusions cover VCS internals, canonical knowledge, runtime/kit state,
common dependency/build trees and recognizable credentials. This is a bounded
allowance for local source transfer, not a universal secret detector: exclude
additional private files explicitly. Source and runtime backups can contain project
content and must receive the same local access protection as the repository.

Changing exclusions removes newly excluded entries from the derived source mirror
on the next complete successful reconciliation; host files remain authoritative.
Deletion is based on a complete verified manifest, never an incomplete scan. Host
symlinks/reparse points are skipped; unsafe archive paths/links, name collisions
and corrupt archives fail validation. An interrupted
apply leaves an importing marker; indexing fails closed until reconciliation
finishes. Import and the entire indexing/publication pass share one lease, so an
index cannot publish a mixture of source generations. Long indexing can delay sync.
OS advisory supervisor/operation locks release on process death.

Native change notifications are hints, with periodic reconciliation and bounded
retry. `PI_WORKSPACE_DEBOUNCE_MS` defaults to 1500 (accepted 100–60000);
`PI_WORKSPACE_VERIFY_INTERVAL_SECONDS` defaults to 300 (accepted 5–86400) for cached
hash revalidation. Changes to configuration take effect when the supervisor restarts.

## Status, backup and recovery

For ordinary operation use the kit's `make platform-status`, Compose `ps`/`logs`,
and the application status response. Workspace status separates synchronized and
indexed generations and reports pending updates, last synchronization and the
last host-verified backup. A completed index is distinct from a synchronized source.
Helper `status` prints its local synchronization record; `workspace-backup-status.json`
records the last completed host snapshot path. Check `workspace-agent.log` for
supervisor/backup errors on Linux.

Backups use application-coordinated SQLite online backup and compatible derived
artifacts, including the active snapshot/profile. They exclude private HOME/chat
settings, credentials and model files. A host snapshot becomes complete only after
manifest/version/profile/checksum verification and final rename. An exported
snapshot is capped at 20 GiB. Retention keeps at most three verified completed
snapshots and prunes toward 40 GiB, always retaining at least the newest good one.
Unverified directories are not treated as usable recovery points.

The default host location is the repository's parent directory under
`ProjectExpert-backups/<workspace-id>/`. `PI_RUNTIME_BACKUP_DIR` may select another
local directory outside the repository. Automatic backup runs after an observed
new index generation and every 30 minutes, with a one-minute minimum between
successful backups. Set `PI_RUNTIME_BACKUP_INTERVAL_MINUTES` (minimum 1) to change
the interval, or `PI_RUNTIME_BACKUP=off` to disable backup. These settings are read
from the environment or `deployment.env` by launchers. Keep operator credentials
backed up separately according to your own policy.

Normal `down` requests backup, stops supervision and stops containers without
removing managed volumes. A failed backup emits a warning and shutdown continues;
that warning is not evidence of a completed recovery point. `stop` stops supervision
without requesting that checkpoint. Never archive a running SQLite database by
copying its live files.

For explicit Linux recovery, from the kit directory, substitute absolute paths:

```bash
sha256sum --check workspace-agent-SHA256SUMS
chmod u+x workspace-agent-linux-amd64
./workspace-agent-linux-amd64 status --repo /work/project --kit "$PWD"
./workspace-agent-linux-amd64 backup --repo /work/project --kit "$PWD"
bash compose.sh down
./workspace-agent-linux-amd64 restore --repo /work/project --kit "$PWD" --backup /work/ProjectExpert-backups/ID/SNAPSHOT
bash start.sh
```

For direct helper commands, export any chosen backup settings explicitly; unlike
launcher functions, the helper does not load all settings from `deployment.env`.
On Windows, use `workspace.ps1` for checked status/backup calls:

```powershell
. ./workspace.ps1
Invoke-WorkspaceAgent status
Invoke-WorkspaceAgent backup
./stop.ps1
# Verify the executable against workspace-agent-SHA256SUMS before direct invocation.
& ./workspace-agent-windows-amd64.exe restore --repo 'C:\work\project' --kit $PWD.Path --backup 'C:\backups\ID\SNAPSHOT'
./start.ps1
```

Restore verifies the snapshot and requires stopped application/supervisor. It
imports into a new inactive runtime volume, selects it in local kit state and
preserves the previous runtime volume. Normal startup then validates or rebuilds
readiness. Restore does not overwrite host source or canonical knowledge. Profile
incompatibility is a rebuild/compatibility issue, not a reason to merge index files.
If source import was interrupted, retry normal startup/reconciliation before
attempting index recovery. If no verified snapshot exists, retain host source and
canonical knowledge and rebuild derived state; do not claim live-volume durability.

## Login lifecycle and acceptance

The default supervisor is session-only. Explicit optional user registration is
`bash workspace-autostart.sh install` (systemd user service) or
`./workspace-autostart.ps1 -Action Install` (Task Scheduler). Remove it with
`uninstall` or `-Action Uninstall`. Launchers never register a login hook. Linux
user service setup does not enable system-wide lingering. Neither these scripts
nor cross-compilation prove reboot/crash recovery on a particular host.

| Evidence area | Current evidence |
| --- | --- |
| Compose CPU/CUDA/Vulkan/native Windows topology and torch/base | Portable rendered-config tests; inference execution is separate |
| Linux Docker source/import/checkpoint and MCP Wiki/restart synthetic exercise | PASS; diagnostic model, see measured evidence |
| 30k-file initial import / one-file update | 18.1 s initial; 48 bytes for one edit; native Linux reads show no volume advantage |
| Windows native helper, PowerShell, GPU and login/reboot lifecycle | NOT TESTED on native Windows |
| Power-loss durability, reboot recovery, hardware GPU throughput | NOT TESTED |

`auto` remains `bind` until measured platform acceptance justifies promotion.

Detailed commands, measured timings and remaining platform gates are in the
[verification record](../openspec/changes/add-managed-fast-workspace/verification.md).

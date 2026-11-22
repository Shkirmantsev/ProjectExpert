# Production source recovery

Use a matching application image and deployment kit. Upgrading the source checkout
or refreshing the browser does not replace an existing application container.
Keep the previous kit, verified asset packs and consistent runtime backup. This
Encoding rules affect the local index and leave the original source bytes intact.

## Search with skipped files

Use the same command from Windows PowerShell 5.1, PowerShell 7 or a Linux shell:

```text
make -C .project-intelligence-deploy platform-start
```

Make passes its default `ALLOW_SKIPPED_SOURCES=1` to the existing policy.
Use `ALLOW_SKIPPED_SOURCES=0` to require a complete index. Direct launch scripts
use `PI_INDEX_REQUIRE_COMPLETE` from the kit's `deployment.env`.

With skips allowed, isolated source failures are recorded and the other sources
continue through embedding and local index publication. Search and MCP can
then use the indexed sources. The page and the REST indexing status report the
coverage. Configuration errors, cancelled runs, model failures and invalid
artifacts still block publication. Git export requires a generation with zero
skips. Run `make -C .project-intelligence-deploy platform-index-failures` for the
private report, repair the affected sources, and select **Update local index**.

## Legacy encodings and languages

UTF-8, UTF-8 BOM and BOM-marked UTF-16/32 work automatically. Languages such as
Ukrainian, German, Japanese and Arabic do not require separate parser modes.
When UTF-8 decoding fails, plain text (including SQL), Java, Markdown and HTML
can fall back to Windows-1251 or Windows-1252. The adapter ranks the candidates
using a bounded sample around the first UTF-8 error and strictly decodes the
original bytes with the selected codec. No configuration is needed for this
path. The detected codec is recorded in the local search records.

For plain text and Java that still needs correction, open
**Settings → Text encoding overrides**. Add a rule, enter a
repository-relative pattern and select the encoding in the form. Preview the
aggregate decoding outcomes, save reviewed rules, then run **Update local index**. One rule covers any number of matching files; no per-file
security approval is needed. For example:

```json
{
  "schema_version": 1,
  "default_encoding": "utf-8",
  "rules": [
    {"pattern": "legacy/**/*.java", "encoding": "cp1252"},
    {"pattern": "historical/**/*.sql", "encoding": "cp1251"}
  ]
}
```

Use the charset that actually produced those files. CP1252 is common for German
Windows sources, CP1251 for historical Cyrillic, and Shift-JIS (`shift_jis`) for
Japanese. Supported alternatives include CP1250–1258, selected ISO-8859 charsets,
KOI8-R/U, CP866, CP932, GB18030, Big5 and EUC-JP/KR. An explicit encoding
override takes precedence over automatic detection. UTF-8, Unicode BOMs and
supported document charset declarations retain precedence.

Patterns are case-sensitive repository-relative POSIX paths, independent of
Windows drive letters or container `/repo` paths. `*` matches a path component,
`**/` zero or more directories. Conflicting rules matching a source are rejected.
No absolute paths, traversal, symlink escapes, unsupported codecs or binary/NUL
payloads are admitted. A preview proves strict decoding, not semantic correctness:
review representative text locally before choosing an ambiguous charset.

Settings stay in the private runtime cache `config/source-encodings.json` (under
`.project-intelligence-cache` by default, or the configured cache root). Managed
Windows mode stores them inside its runtime volume; the browser saves them in the
correct runtime location. They are not Git-portable configuration. Keep a separate
approved private copy if needed when transferring an installation. On another PC,
configure the same reviewed policy before restoring/reindexing its affected
sources. An incompatible portable source pipeline is reparsed; it is not silently
accepted under a different decoder.

Editing an override changes only the matching source compatibility keys. The
first refresh after upgrading the automatic decoder revalidates its supported
text families. Compatible embeddings remain reusable. A warm unchanged reindex does no new parsing or
embedding for compatible completed sources. Parser workers remain parallel and
resource bounded. Confidential text remains searchable locally and through MCP;
existing safe-fragment export checks still run on decoded text. A decoding rule
never grants permission to export protected text or vectors.

The administrator API provides GET (policy and retry status), POST (preview) and
PUT (validate, preview and save) at `/api/v1/admin/source-encodings`. It uses the
same local-owner/token authorization as other administrative operations. Tokens
remain optional when the local installation has not configured `PI_UI_TOKEN`.
Saving rules does not run Reindex or Git commit/push automatically.

## Failed jobs and readiness

Typed permanent/configuration/internal source failures block automatic retry of
that same candidate, including after restart. Fix a source or change its encoding
policy to make it eligible again, or explicitly run Reindex for one further
attempt. Typed transient failures back off with a five-attempt limit. Existing
untyped callback failures retain their established retry behavior for compatibility.
The private `index-retry.json` contains hashed candidate identity, aggregate
categories and retry time, without document text. It is visible in the encoding
settings status. Existing SQLite ingestion job progress/history remains authoritative
for actual source-stage results; this small file is retry coordination, not a
replacement job queue or durable index.

Complete publication still requires every selected source to succeed. The prior
published generation is retained if a new candidate fails. A first installation
without a good index remains unready. **Service URL** means the control plane can
be reached; inspect `/health/ready` and the UI index status for search readiness.
Use `./wait-ready.ps1` or `bash wait-ready.sh` as an explicit bounded index-ready
step for deployment/CI; ordinary startup does not wait indefinitely for a large
index. Existing readiness rules block retrieval during a running or failed refresh,
even while the prior durable generation is retained. For a complete index,
use `ALLOW_SKIPPED_SOURCES=0` with Make or `PI_INDEX_REQUIRE_COMPLETE=1` for direct launches.

## Workspace shutdown and exclusions

Both scanners prune generated `.claude/worktrees` trees, including nested copies.
Authored `.claude/commands` and ordinary documentation remain. No worktree files
or Git refs are deleted. Git's local excludes do not govern Python filesystem
scanning; generated-checkout correctness no longer requires manually appending
to `.git/info/exclude` with PowerShell's platform-dependent text encoding.

Normal shutdown requests quiescence before waiting on operation locks. Scans can
stop between files; an active importer finishes its safe atomic boundary. A
15-second deadline (configurable with `PI_WORKSPACE_STOP_TIMEOUT_SECONDS`, 1–120)
returns `STOP_PENDING` rather than killing the writer or shutting containers down
under it. Inspect `workspace-operation-status.json` and retry after completion.
Do not delete lock files or volumes. OS locks release after their owners exit.

Normal stop keeps existing verified scheduled snapshots and does not start a new
full backup. Use `./stop.ps1 -Backup` for explicit quiesce, backup and stop. Backup
failure aborts shutdown and remains visible. See [workspace guide](FAST_WORKSPACE.md).

Windows `auto` uses managed volumes. Linux `auto` uses volumes for WSL `/mnt/<drive>`
paths and bind mounts elsewhere. Explicit `bind` and `volume` retain their meaning.

## Offline assets and GPU diagnosis

No host download, driver change, TLS bypass or relaxed SHA/license check is added.
Native setup verifies a newly extracted staging directory before activation.
`accelerator/asset-verification.json` records app/asset pins, expected manifest SHA,
requested backend, verifier category and exit code. Categories include missing or
unreadable asset, manifest/hash mismatch, blocked release, production-lock/runtime
mismatch and missing Docling assets. Diagnostics omit source contents and host
paths; a valid relative asset name may identify a corrupt pack member.

A preserved `deployment.env` can retain an old explicit app/asset pin. Review the
matching kit/application/assets rather than replacing private settings wholesale.
After resolving the reported cause, explicit
`./setup-windows-accelerator.ps1 -RepairAssets -Backend vulkan` stages and verifies
a replacement. A previously cached pack remains intact until replacement
verification succeeds, and is preserved as `.previous-<id>` afterward. This option
repairs extraction; it does not approve an unreviewed CUDA pack. Default native
Vulkan, separately reviewed operator-local CUDA, container CUDA and CPU selection
remain available through the existing launcher contract.

The native serving listener is `0.0.0.0:8769` for authenticated container-to-host
access. Restrict Windows Firewall to the intended Docker/WSL peers; never expose
it to unauthorized LAN clients. See [native GPU recovery](../distribution/deployment/WINDOWS_NATIVE_GPU_RECOVERY.md).

## Verification limits and work-PC pilot

Synthetic multilingual fixtures and pinned production Java-worker tests establish
software behavior. They do not establish the charset of the reported 57 files.
On a backed-up work-PC test checkout, verify zero failed sources with completeness
on, correct representative search results, warm no-op reuse, one-source edit,
stop/restart and prior-generation retention. Record only sanitized counts and
categories; never upload corporate documents to public CI.

The original native-pack verification cause, physical MX550/Intel performance,
NTFS behavior under corporate load and a first real no-egress PDF remain separate
work-PC acceptance gates. Run the paired release with public model downloads
blocked and verify OCR/layout/table/figure extraction using the already-reviewed
asset pack. Passing software fixtures is not certification of these external gates.
Rollback keeps the prior image/kit, restores reviewed private policy and reindexes
affected sources; no rollback deletes source files, SQLite/WAL, volumes or Git history.

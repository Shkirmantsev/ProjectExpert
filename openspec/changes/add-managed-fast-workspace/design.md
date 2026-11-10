# Design

## Current state

Checkout is feature/generate-init-project at 32c0c1b, not the supplied dev baseline. Source is mounted at /repo; application derives cache there. Bootstrap uses a project lock and content identity checks, but an importer currently does not participate. SQLite state spans multiple databases plus JSON, objects, graph and ANN generations. Wiki writes use canonical host paths.

## Proposed design

Keep accelerator configuration untouched. A standard-library Go host helper uses the selected local Docker context, deterministic project identity, native filesystem capture, manifest/tar batch transport and a restricted application-image importer. Only source/runtime mount topology changes. Canonical knowledge remains a direct host bind.

Importer staging verifies all bytes before live mutation. A durable importing intent precedes mutation. The importer and application share .projectexpert-workspace/commit.lock for the entire apply and entire index construction/publication respectively. This corrects the document's start/end-only TOCTOU: a final marker check alone cannot protect publication. Failed apply is fail-closed until replay/reconciliation; atomic per-file replacement is never represented as directory atomicity.

Import durability uses Linux syncfs at verified-stage and applied-tree boundaries, with one descriptor opened before writes to observe asynchronous writeback errors. Root ownership is established before these barriers.

Checkpoint coordination uses the existing project writer lock plus SQLite transaction barriers and immutable-file verification. SQLite online backups and compatible derived files are assembled into a checksummed snapshot; private settings/HOME/model credentials are excluded. Host completion and inactive restore validate manifests. Private credentials are operator-owned configuration, not derived cache.

## Affected modules / interfaces

Host: tools/workspace-agent, deployment workspace scripts, compose wrappers, exporter and kit Containerfile. Product: workspace sync contract, restricted importer, version reader/identity, bootstrap publication, status extension and runtime checkpoint adapter. Tests exercise contracts without changing parser/retrieval or MCP tool schemas.

## Data / persistence / concurrency impact

Host source/canonical authority is preserved. Live derived state stays in Linux volume. No remote daemon transfer, bidirectional source sync, live database tar, daemon socket mount or automatic volume deletion. Host source changes may wait through a long indexing lease; this is the deliberate minimal correctness tradeoff.

## Compatibility and migration

Auto defaults to bind pending Windows/Linux real-world acceptance. Explicit volume requires compatible new application image and helper. No installation migration. Existing inference and endpoint contracts are preserved.

## Fail-closed mode identity

Base Compose forwards PI_WORKSPACE_MODE so an explicitly managed app can reject
missing control metadata instead of silently treating a damaged mirror as bind.
The storage overlay still changes mounts only. Existing bind/auto defaults do not
change. Generation metadata remains authoritative for content and VCS identity.

## Narrow durability correction

The existing Wiki atomic writer flushed language buffers but did not fsync the
file or renamed directory. Approved materialisation also used direct shard/manifest writes; those now use durable atomic replacement. A failing regression proved that a successful write
could precede durable storage. The implementation adds file and POSIX ancestor-directory
sync barriers without changing revision, approval or content semantics. Windows
host filesystem and virtualized bind durability remain native acceptance gates.

## Risks and rollback

Windows hardware and login lifecycle require actual acceptance; builds/tests do not prove deployment support. Unattended recovery is advertised only after a per-user startup hook is installed. Bind remains the fallback for new installs. Restore never replaces an active runtime in place.

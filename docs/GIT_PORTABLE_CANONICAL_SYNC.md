# Git-portable production knowledge

The opt-in portable/v2 path connects published resumable indexing results to
approved Git text and restores those results into indexing-state.sqlite before
parsing. It preserves the existing v1 reader and local SQLite backup protocol.
See [evidence](GIT_PORTABLE_CANONICAL_EVIDENCE.md) and
[ADR 0034](../.ai/wiki/adr/0034-portable-production-canonical-snapshots.md).

## Ordinary workflow

Use the target checkout, not the ProjectExpert application directory. Enable
portable identity and automatic private proposals for initial indexing:

```bash
PI_PORTABLE_EXPORT=review python -m pi_platform.cli reindex --target /repo
python -m pi_platform.cli canonical export --target /repo --include-vectors
python -m pi_platform.cli canonical status --target /repo
```

`export` only stages a private proposal and prints stagingId, snapshotId, source
coverage, excluded source IDs, sizes and changed paths. `--include-vectors` selects
exact float32 JSON vectors; omitting it means a cold cache computes document
embeddings. Review sources, coverage and changed paths before approval. The
`canonical status` command verifies the checked-out snapshot, not pending staging.
The indexing response/UI status exposes the automatic proposal and import counts.

Use an operator-issued signed `materialise` token scoped to the target repository
and the proposal snapshotId. Publication rechecks source version and generation:

```bash
python -m pi_platform.cli canonical publish --target /repo \
  --staging-id STAGING_ID --approval-token "$APPROVED_TOKEN"
python -m pi_platform.cli canonical verify --target /repo
git -C /repo diff -- project-knowledge/
```

The product never stages or commits Git files. The developer can review and commit
the canonical diff, then clone/switch branches normally. On the other checkout:

```bash
python -m pi_platform.cli canonical hydrate --target /other-checkout
```

`canonical hydrate` runs the normal version-fenced production bootstrap, importing
compatible source results before parsing and rebuilding local FTS/graph/dense
indexes as needed. Existing `reindex`, `hydrate`, `make platform-reindex` and
`make platform-hydrate` retain their meanings: legacy `hydrate` verifies v2 but
only production indexing seeds resumable state. Query through the existing MCP or
REST retrieval interfaces once bootstrap reports ready. Changed or absent sources
are misses; old branch results never enter current generation membership.

The existing `materialise` command supports `--from-active-index --preview` and
`--from-active-index --staging-id ... --approval-token ...`. Without the selector
it retains the legacy change-list route; an empty list is never a populated export.
REST `/api/v1/materialize` adds `from_active_index`, `preview`, `include_vectors`
and `staging_id`; existing role/policy and signed approval checks still apply.

## Explicit automatic publication

`PI_PORTABLE_EXPORT=approved-auto` stages and publishes only when
`PI_PORTABLE_APPROVAL_TOKEN` verifies through the configured
`PI_OPERATOR_APPROVAL_KEY`. Issue that token through the existing trusted approval
boundary for action `materialise`, the exact resolved repository root, an explicit
expiry, and permitted snapshot IDs. An empty change-ID scope is a deliberate
repository-wide capability; use it only if the operator approves future snapshots
for that project within the validity window. Never commit keys/tokens to config.
Every publication checks the capability again, including expiry, before replacing
the root. A random environment token does not grant access.

`PI_PORTABLE_VECTORS=1` includes vectors in automatic proposals. Query readiness
and export state are separate: `pending-review`, `published`, `failed` or `off`.
A rejected export retains the successful local index. Successful auto publication
acknowledges the new canonical fingerprint to avoid a monitor refresh loop.

## Format, bounds and privacy

Root: `project-knowledge/manifests/portable-v2.json`, schema `portable/v2`.
Root fields: schema, fileCap, records, children, snapshotId. Identity hashes the
canonical root without snapshotId. Child descriptors contain path, sha256, bytes,
type and (for JSONL shards) records. Pages contain children recursively. Shards
contain canonical UTF-8/LF envelopes `{kind,id,body}`: source summaries with exact
pipeline/metadata identities; SHA-addressed original canonical payload text;
and optional vectors with exact profile/model/text/dimension/normalization.

Generated files live only under `objects/portable-v2/`, `manifests/portable-v2/`,
the root descriptor and two narrowly scoped Git attributes files. Each file is
bounded by `PI_PORTABLE_SHARD_MIB` (1–16; default 8). Configure total bounds with
`PI_PORTABLE_MAX_TOTAL_MIB` (at most 2048) and `PI_PORTABLE_MAX_FILES` (at most
100000). One source result is limited to 64 MiB; oversized records/summaries fail
explicitly. Import and verification also enforce hard bounds. No truncation,
binary compression, LFS fallback, live SQLite copy, ANN or model export occurs.

LOCAL_ONLY, REFERENCE, unknown policies, private/tmp paths, restrictive security
classes and denied co-owned derivatives are excluded or rejected before Git
writes. Unknown/unresolved graph or document references fail verification. Known
credential signatures fail export, but operator source review is still required.
Derived canonical trees are pruned from discovery; authored Wiki remains indexed.
Host paths never become portable identities. Source *bytes* must match: differing
source CRLF/LF bytes are an intentional miss; configure source attributes if exact
cross-OS byte identity is required. Generated attributes preserve canonical bytes.

## Upgrade, failure and rollback

Unconfigured installations retain existing cache keys and defaults. First enabling
portable identities reprocesses old absolute-path results once; old SQLite rows
and v1 files remain intact. No source conversion or volume deletion is automatic.
Back up local state using the approved [indexing recovery](INDEXING_STATE_RECOVERY.md)
protocol. Binary backups are local recovery artifacts, not Git-portable snapshots.

Verification is strict: missing files, duplicate envelope IDs, unsafe/linked paths,
wrong hashes/counts, dangling references and invalid vectors prevent import or
publication. Existing immutable files remain available; source imports preserve atomic per-source savepoints in bounded commit groups
and can retry after interruption. Publication verifies the
installed immutable tree before replacing the root; failed root replacement keeps
the previous pointer. New immutable files left after interruption are unreferenced.

`canonical repair --staging-id ... --approval-token ...` republishes an authorized
current proposal through the same verifier. It can restore corrupt hash-addressed
files from a valid stage; it does not guess missing content, rewrite v1, remove
Wiki or discard caches. A stale stage requires reindexing/restaging. If the current
root is corrupt and prevents reindexing, restore the reviewed canonical snapshot
using Git, or reuse a valid stage for the same source version/generation.

Disable export with `PI_PORTABLE_EXPORT=off`. Existing v1 stays readable. To roll
back to an older reader, explicitly check out the prior reviewed canonical tree
and use the matched application/backup; retain all volumes and user settings.
Private staging and unreferenced historical canonical files are retained for
review; there is no automatic cleanup. Monitor polling follows the v2 root rather
than rehashing immutable shards; `canonical verify`, import and startup detect
shard corruption. Background bit-rot auditing is not implemented.

## Deployment limits

No Docker/GPU/model packaging behavior changes. Portable text obeys existing bind
mount/managed workspace fences. Host write-back from isolated volumes still uses
the existing approved synchronizer; no new automatic host writer is supplied.

Text/code results and document structure are supported where source provenance
is complete. Image-only sources lack resumable source results and cannot form a
complete portable proposal. PDF figures needing parser-private binary assets
cannot promise cold-clone reuse from text alone. Real Docling/Java/offline-model,
physical Windows/Rancher/CUDA/Vulkan and million-source production acceptance
must be reported separately; local hashing-model tests do not certify them.

## Performance controls and repeatable measurements

Source parsing retains the existing resource-aware concurrent scheduler. On the
verification host, 16 effective CPUs admitted 12 source workers; the production
fixture observed 12 pending workers, and a barrier test proves actual concurrent
parser entry. `PI_PARSE_WORKERS` / `PI_INDEX_WORKERS` and `PI_CPU_TARGET_PERCENT`
remain operator controls. Memory admission can reduce concurrency deliberately.
PDF process workers retain their existing separate `PI_PDF_WORKERS` /
`PI_PDF_THREADS` controls and measured-memory admission; heavy native PDF work
is not automatically assigned the lightweight text-source worker count.

A production index run verifies the portable snapshot once and shares the private
read-only plan across source and vector import. Bootstrap defers portable
verification to that locked indexer; standalone hydrate still verifies strictly.
Warm compatible sources do not recommit payloads. Vectors are compared in batches
and unchanged bytes are not rewritten. Fresh portable imports group at most 64
sources / a 16 MiB target per durable transaction, with one savepoint per complete
source. One larger source may exceed the target up to the 64 MiB source limit.
An interrupted uncommitted text group replays from Git without parser work;
original heavy parser checkpoints retain their immediate source durability.

Manifest verification batches canonical envelope insertion without encoding the
same record twice. Publication validates staged semantics once, then verifies
installed immutable byte hashes before root replacement. It does not reparse the
entire corpus into repeated SQLite spools for each publication phase. Full
corruption, reference, scope and version checks remain enabled.

Developer benchmarks are reproducible from the repository checkout:

```bash
python3 scripts/benchmark_portable_sync.py production
python3 scripts/benchmark_portable_sync.py format --records 1000000
```

The first runs real Git/SQLite indexing against 50 synthetic Markdown sources
with hashing embeddings, including warm, both cold-clone modes, 5 changed sources
and branch return. It reports source/model counters, worker admission, storage
and elapsed times. The second measures format-only streaming/count/hash/size
behavior; it does not certify a million-source production index. Host load and
real model/document costs matter; counters and integrity are the acceptance gates.
The legacy mutable graph's single-upsert API still rewrites its prefix shard;
production graph candidates and portable export use bulk/streaming builders.

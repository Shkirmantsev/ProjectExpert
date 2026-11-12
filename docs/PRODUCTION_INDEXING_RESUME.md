# Production indexing recovery

This is a staged implementation of the user-supplied production indexing V2
design. The active change is
[implement-production-indexing-resume](../openspec/changes/implement-production-indexing-resume/proposal.md).
Existing accepted requirements remain in [CURRENT](../openspec/CURRENT.md).
The new engine is opt-in pending the release gates below; it never silently
falls back to a full legacy rebuild.

## Run and observe

For a direct CLI process, set these variables in its environment:

```bash
export PI_INDEX_ENGINE=resumable
export PI_INDEX_PARALLEL=1
export PI_EMBED_BATCHING=1
```

Compose operators set the corresponding values in `deployment.env`; the kit
forwards these switches into the application. Defaults remain `legacy`, `0`,
and `0` until migration/restore, pinned server and target-platform acceptance.
`PI_INDEX_REQUIRE_COMPLETE=1` is the resumable default: failed sources or
unsupported images block the candidate. An explicit `0` allows incomplete
results with `source_failures`; it does not convert failures into successes.

The public `index_repository()` signature and existing `runtime.extra` fields
are preserved. The runtime remains unpublished until the existing caller
validates the source version and commits its snapshot. Caller publication now
holds the indexing lock and rejects candidates superseded by a newer fence.

`GET /api/v1/indexing-status` includes `indexes.retrieval.indexing_progress`:
job identity, fence, state, active stage, total/completed/failed/degraded counts
and update times. Counts follow committed sources/vector batches, exact rows
and completed graph shards. No unmeasured ETA is presented. Source admission
reports bounded CPU workers and estimated queued memory through runtime metadata.

## Durable boundaries

`indexing-state.sqlite` stores immutable canonical payloads, source summaries,
source-version ownership, candidate generation membership, jobs, stages and a
monotonic builder fence. WAL, FULL synchronous writes, foreign keys and startup
quick-check are mandatory. Reads verify persisted checksums. A worker's private
source buffer becomes visible only when its final completion transaction commits.
Cancellation or failure discards the private buffer. An OS advisory lock prevents
simultaneous builders; an old heartbeat never authorizes taking a live lock.

Source compatibility includes its bytes, pipeline key and metadata. Deleted
sources and old source revisions do not enter the new candidate. Previous
candidate memberships are preserved. Canonical payloads use full serialized
hashes in the durable driver: the legacy raw-text projection key intentionally
omits metadata and cannot safely identify an immutable complete record.

On first resumable use, legacy `ingestion.json` is backed up as
`ingestion.pre-resumable.json` and imported source by source. Orphaned records
are ignored; the original JSON and existing embeddings stay intact. A different
pre-existing migration backup fails closed. A bounded standard-library reader spools legacy records into temporary SQLite
tables, then imports one complete source at a time. Both migration and production
reads avoid reconstructing the whole legacy cache; individual legacy entries
above 64 MiB fail with a bounded-migration diagnostic.

Exact FTS uses committed idempotent batches in `<hash>.building.sqlite`,
reconciles authoritative row hashes, checkpoints and backs up into a standalone
closed database, verifies integrity/counts, fsyncs, then promotes on the same
filesystem. It never renames a main file still dependent on a live WAL. Graph
records are grouped by deterministic shard and each shard is atomically written
once; restarts verify checksums and reuse completed shard bytes. The separate
BM25 index is still rebuilt in memory and reported as the sparse stage.

Vector reuse remains profile-scoped in `indexes/embeddings.sqlite`. Batches
cover cache lookups, role-aware requests, segment aggregation, validation and
SQLite persistence. HTTP text requests can contain multiple strings; images
remain isolated. The conservative UTF-8 token bound may produce smaller batches
than an exact local tokenizer. Committed vectors survive a failed dense build.

## CPU and parsing

The default CPU budget is 80% of the tightest detected affinity, host or cgroup
capacity. A shared token pool bounds concurrent source tasks. Memory admission
uses host/cgroup remaining memory and conservative source estimates; unknown or
oversized sources run alone. These estimates do not enforce a hard RSS ceiling.
Default stateless adapters use bounded threads; Java remains in crash-isolated
subprocesses. PDF/Docling is serial by default. With `PI_INDEX_PARALLEL=1` and
`PI_PDF_WORKERS>1`, spawned source workers construct their own SQLite/Docling
objects after thread limits are set. `PI_PDF_THREADS` and memory estimates bound
admission. Workers return checksummed bounded source spools; only the coordinator
commits complete canonical results. Actual model RSS and OS acceptance remain
release gates. No fixed parse-speed improvement is claimed.

Native Java parser corruption, crash or exhausted parsing failure can retain
explicitly degraded source text without AST-derived entities/edges. Required
parser configuration errors still fail. HTML and permitted legacy text support
BOM/UTF-8 and bounded cp1252/Latin-1 fallback with decoding provenance; binary
input is rejected. DOCX and PPTX have bounded OOXML text extraction; XLSX and
legacy binary Office formats are explicitly unsupported. Extraction does not
claim Office layout/table understanding.

## Recovery and rollback

Stop the application before restoring state; the builder lock cannot evict
serving query handles. Use [state operations](INDEXING_STATE_RECOVERY.md) for
verified SQLite backup/restore, including interrupted restore recovery. A restore
journal blocks indexing until recovery completes. Existing vector namespaces
remain reusable. Failed candidates never replace served exact/graph/dense
artifacts. Canonical project sources are not part of generated-state restoration.

For code rollback, restore the previous immutable application/kit image and its
matching state backup. Switching `PI_INDEX_ENGINE=legacy` deliberately reuses the
retained JSON; work completed only by the new engine is absent from that JSON.
It is an operator rollback, not automatic recovery presented as resumed work.

Generation cleanup is an explicit, journaled operator command; automatic GC
remains disabled. It preserves durable active/previous publication pointers,
newest ready and compatible unexpired attempts, and shared canonical payloads.
Prepared publication intents protect candidates across a crash between filesystem
snapshot commit and SQLite pointer update; unresolved intents remain retained.
Runtime artifact files are retained until a reader-safe deletion protocol exists. Disk preflight reserves candidate room using source size, 64 MiB minimum
and one percent free space. Later SQLITE_FULL/IO errors still abort the candidate.
Managed workspace checkpoints also retain the new indexing state and exclude
concurrent builders. Manage old artifacts offline after verified backup; never delete files used by
an active reader. Bounded automatic generation/artifact GC is not implemented.

## Deployment and release limits

Liveness now checks `/health`; `/health/ready` remains separate and optional
wait-ready scripts can await retrieval. Existing HTTP startup already ran ahead
of indexing. Host public roots are collected and merged with image roots; TLS
verification stays enabled. Engine registry trust must be fixed before any pull;
container roots cannot repair bootstrap trust. Windows and WSL source defaults
choose the managed volume; explicit workspace configuration retains precedence.

The offline remediation now requires mandatory digest-addressed seeding before
setup and startup, local-only model/PDF/tokenizer/torch consumers, native Windows
OCI extraction, and network-denied production promotion gates. The
[asset lock](../distribution/assets/assets-lock.json) and
[release identity](../distribution/assets/asset-release.json) remain honestly
blocked: the actual complete reviewed pack and published OCI digest are still
missing. Default installation therefore fails with a missing offline asset
message; it no longer downloads as a fallback. This is not yet a usable offline
release. See [assembly/review instructions](../distribution/assets/README.md).
Existing data is preserved, and explicit kit upgrades preserve deployment.env
while diagnosing missing or mismatched release pins.

The old fixed 1.10 accelerator threshold is removed. Managed Auto now retains
three actual query-corpus throughput rounds and scopes its evidence to the live
controller session; query measurements do not certify document-index throughput. Evidence-based resource
policy requires supported, healthy, admitted, quality-validated resources and
repeated measurements with matching workload/runtime identities. Existing Hybrid
means GPU backbone plus CPU projector, not parallel multiendpoint embeddings.
The optional `MultiEndpointEmbeddingModel` and factory API accept only explicit
pre-authorized endpoints, exact live identities and distinct physical devices.
Their document-workload benchmark requires numerical, individual and combined
top-k parity plus repeated combined throughput above all standalone samples.
Dispatch bounds in-flight work, preserves order and retries only missing work.
`PI_EMBED_MULTI_BACKEND` defaults to `0`; there is no automatic endpoint discovery
or hardware certification. Query requests remain on the validated baseline.

Release remains blocked on actual packaged SQLite safety verification, real
pinned llama batching/tokenizer and Docling offline smoke, complete licensed OCI
assets, physical CPU/CUDA/Vulkan comparisons, Windows PowerShell 5.1/7 with both
Rancher and Docker Desktop, OS power-loss/disk-full/corruption testing and the
large-corpus benchmark. The accepted readiness gate also still refuses stale
cross-version serving during refresh/failure: old artifacts remain intact but
automatic last-good UI serving requires an explicit version-safe contract change.
These are material differences from the attachment's complete production target.

## Reproducible fixture check

`python scripts/benchmark_indexing.py` writes a local report for identical generated
Markdown input across legacy, resumable serial and resumable parallel modes, with
cold/warm runs and canonical-generation equivalence checks. The fixture explicitly
uses hashing embeddings; its wall times do not represent production Gemma/Docling
or EdkWmsXTotal throughput. Reports stay under `tmp/local/indexing-benchmark/`.

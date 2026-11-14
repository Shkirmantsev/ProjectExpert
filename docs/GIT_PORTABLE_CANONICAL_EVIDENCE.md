# Portable canonical evidence

Initial branch evidence: feature/generate-init-project, af632b4544e620373ad5dd32013d1c68a21897da.
The supplied document's dev baseline is not this branch's identity. No dev fetch,
branch switch, remote publication or hardware certification is implied.

| Gap | Observed function | Reproduction / planned proof | Fix |
|---|---|---|---|
| 01 | MaterialiseService.materialise_durable_changes; CLI/REST pass no changes | published generation export; empty request reports no materialisation | explicit active-index selector |
| 02 | HydrateService.restore_runtime uses RuntimeCache | clone index with parser patched to fail | import into SqliteIngestionCache before run_many |
| 03 | HydrateService._hydrate_family JSON-only; LocalShardedGraph.rebuild_manifest prefix hash | JSONL body SHA and reader checks | versioned v2 envelopes; explicit legacy JSONL |
| 04 | LocalShardedGraph._write_shard_line unbounded in-place write | inspect actual shard.jsonl; oversize rejection | capped atomic writer; bounded v2 pages |
| 05 | RepositorySourceDiscovery defaults lack generated exclusions | generated tree excluded; Wiki admitted | prune generated subtrees |
| 06 | hydrate increments hits after misses and skips missing/hash-invalid shards | cold=0 warm=1; corruption failure | strict default, explicit permissive legacy mode |
| 07 | production always calls source driver; current memberships isolate generations | Git A-B-A, deletion, dirty, worktree | compatible source seeding and existing generation selection |
| 08 | vector store is binary local-only | float32 equality; cold clone document inference counter | opt-in text vectors |
| 09 | pipeline_key includes source.uri; document_result uses absolute sourcePath | independent roots yield same exported bytes | opt-in portable source identity |
| 10 | no production Git clone roundtrip test | actual git clone committed production output | dedicated integration suite |

Results and release limitations are recorded below after execution.

## Delivered implementation and verification

Implementation commit: `2baeb36` on `feature/generate-init-project`; contract commit
`b707a91`. No remote push/PR or deployment was requested or performed. This is a
verified opt-in software implementation, not completion of every release gate in
the supplied design. The OpenSpec change remains active.

| Check | Actual result |
|---|---|
| `PHASE3_SKIP_50K=1 python3 harness.py check` | PASS: 154 suites, 2,013 tests, 17 skips; includes configuration, session, Wiki, strict OpenSpec, capability inventory, MCP core and artifact gates |
| Actual 50,000-node graph fixture in preceding `python3 harness.py check` | PASS: actual emitted JSONL counts, byte SHA256 and 8 MiB caps; about 527 s for the legacy single-upsert fixture |
| Final `python3 -m unittest tests.test_portable_canonical_sync tests.test_sqlite_ingestion_cache tests.test_resumable_repository_indexing -q` | PASS: 52 tests, including the final source-race and generated-metadata guards; portable suite contains 29 tests |
| `python3 harness.py openspec-check` | PASS: 95 items, zero failures; installed strict OpenSpec validator ran |
| `python3 scripts/artifact_manifest.py verify`, session verify, `git diff --check` | PASS before implementation commit; repeated for final documentation/checkpoint |

The full harness preceded the final two focused regressions; the 52-test run
exercises those final changes. The 50k fixture was not rerun after its successful
execution because later changes affect portable source import/verification, not
its Linux graph output. The graph test now closes its inspection handles
explicitly. Initial sandbox socket denial was resolved by running authorized local
HTTP tests outside the restricted socket sandbox. An old launch smoke assertion
that an empty materialise call means `materialized=True` was corrected to the
requested truthful no-change result. Early incomplete runs are not counted as PASS.

### Real Git/SQLite production fixture

Command: `python3 scripts/benchmark_portable_sync.py production`.
Fifty synthetic Markdown sources, real durable source/vector stores and temporary
Git commits/clones/branches, hashing embeddings. The observed effective CPU capacity
was 16 and the resource-aware source worker limit/peak pending count was 12.

| Scenario | Seconds | Parser calls | Parse hits | Document embeddings | Vector hits |
|---|---:|---:|---:|---:|---:|
| Initial | 0.513 | 50 | 0 | 50 | 0 |
| Warm | 0.326 | 0 | 50 | 0 | 50 |
| Cold clone with full vectors | 0.557 | 0 | 50 | 0 | 50 |
| Cold clone without vectors | 0.577 | 0 | 50 | 50 | 0 |
| Branch changing 5 of 50 | 0.372 | 5 | 45 | 5 | 45 |
| Return to original branch | 0.287 | 0 | 50 | 0 | 50 |

That measured run preceded the final bounded-commit import optimization; the
optimization has a separate SQL transaction-count proof below. These small hashing
fixtures certify reuse and scheduling, not real Docling/model throughput. Earlier
pre-optimization observations were warm 0.712 s, full-vector cold clone 0.870 s,
and branch return 0.599 s. Host load differed: these are observations, not a
controlled percentage speedup or a hardware-independent timing guarantee.

Full snapshot: 414,328 bytes / 233 files. Standard snapshot: 288,243 bytes / 183
files. The temporary repository retained 309 loose Git objects / 1,264 KiB after
the benchmark history; historical immutable/vector files were deliberately retained.
No binary runtime artifacts entered canonical Git output.

Deterministic performance gates in the regression suite:

- One verification plan per production index run, shared by both import stages;
  bootstrap does not repeat full verification beforehand.
- Zero warm source payload transactions and zero nonempty vector writes; unchanged
  parsing and document embeddings remain zero.
- A real production adapter barrier proves two concurrent parser threads; existing
  PDF process tests prove separate worker PIDs and no reparse on source reuse.
- Sixty-five verified source imports require two durable SQLite commits, with
  per-source savepoints; an interrupted later group preserves previously committed
  complete sources. Ordinary heavy parser checkpoints still commit immediately.
- Publication checks installed immutable hashes instead of repeating complete
  semantic decode/spool passes. Corruption, staged-file mutation and root-last
  publication remain fail-closed.

### Million-record format benchmark

Command: `python3 scripts/benchmark_portable_sync.py format --records 1000000`.
Actual result: 1,000,000 records, 260 files, 269,835,604 total bytes, maximum file
1,098,324 bytes, spool 23.155 s, write 7.684 s, verify 18.431 s, peak process RSS
32,124,928 bytes (about 30.6 MiB). Exact record count, hashes and file caps passed.
An earlier writer/reader run used 22.562 / 14.186 / 26.596 seconds for the same
record/byte counts. Repeated encoding was removed and verified SQL inserts batched;
wall-clock differences also include host load. This benchmark is format-only:
it does not certify million-source production parsing, graph activation or queries.

## Feature and acceptance matrix

| Area / design tests | Delivered and verified | Limits / not certified |
|---|---|---|
| GAP-01 / production bridge | Published-generation projection, automatic private proposals, explicit CLI/REST selector, signed manual and automatic publication | Media-only source coverage is rejected, not silently truncated |
| GAP-02 / T-05 | Actual source outputs/memberships imported into indexing-state.sqlite before parser scheduling; cold-clone parser counter zero | runtime.db remains the compatible v1 read model; production publication owns active projections |
| GAP-03 / T-04 | Versioned text reader; v1 JSONL byte SHA/count checks; strict cold/warm metrics and v1 tests | Invalid legacy prefix-as-hash manifests must be regenerated; no implicit v1 rewrite |
| GAP-04 / T-01,02,13 | Actual legacy graph file cap/hash test; segmented v2 shards, recursive manifest bounds, oversize rejection; million-format count proof | 200k-edge and million-source production/RSS gates not run; legacy single-upsert API still rewrites prefix shards |
| GAP-05 / T-11,20 | Generated subtrees pruned, authored Wiki admitted, zero diff on repeat export, auto publisher acknowledges its own root | Root-based polling does not detect latent immutable-file bit rot; explicit verify/startup does |
| GAP-06 / T-12 | Corrupt/missing data fails before import/publication, truthful hits/misses and no-change materialise response | Reader reports errors through PortableSnapshotError/CLI JSON, not a new multi-category report protocol |
| GAP-07 / T-07,08,09,10,18 | Real Git clone, A-B-A, deletion, dirty edit, detached worktree; 5/50 changes; source byte guards prevent parse-time cache poisoning | 5/50k production benchmark and exhaustive concurrent-checkout/power-loss injection remain unexecuted |
| GAP-08 / T-06,15 | Optional exact float32 vectors with profile/text/content guards; cold document embedding calls zero; finite/dimension/norm rejection | Real Gemma/USearch semantic parity/offline smoke not rerun for this feature; query/health embeddings are expected |
| GAP-09 / T-03,14,19 | Fresh independent roots produce identical snapshots; autocrlf checkout proof; reserved/colliding/traversal/linked names rejected; restrictive policy and credential/generated-path guards | Physical cross-OS byte comparison remains a CI/deployment gate; unknown secrets still require operator source review |
| GAP-10 / T-17,21 | Dedicated real-Git production roundtrip tests, staged binary injection rejection, interrupted source import/root write, signed repair/retry | Hosted cross-OS jobs have not run on these commits; physical installation/rollback acceptance remains pending |
| T-16,22 / deployment | No live database copy or model/runtime/deployment defaults changed; existing workspace/offline unit suites pass | Physical Docker volume write-back, corporate Windows/Rancher/TLS, CUDA/Vulkan and real offline assets are NOT RUN |

### Deliberate deviations and remaining work

- Default export stays off; review/approved-auto are explicit opt-ins. Approved-auto
  uses the existing signed action/repository/expiry boundary, verified on every
  publication, rather than inventing a second persistent capability authority.
- Enabling portable identity intentionally reprocesses old absolute-path outputs
  once. Unconfigured caches remain compatible and old source rows/files survive.
- Recursive immutable manifests and deterministic segmented prefix buckets replace
  adaptive prefix depth. No record is split; oversized records fail explicitly.
- Pure-text imports use bounded commit groups with atomic source savepoints so a
  large clone does not incur one fsync per source. Only an interrupted text group
  replays; heavy parse durability is unchanged.
- REFERENCE text is excluded conservatively. Denied co-ownership or unresolved
  graph/document dependencies cannot become a partial, apparently complete source.
- Image-only source results and PDF figures that require parser-private binary
  assets are unsupported for complete portable proposals. Ordinary local indexing
  remains available; no hidden binary/base64 export is introduced.
- Managed volume-to-host publication still belongs to the existing synchronizer;
  no new approved automatic host write-back adapter is delivered here.
- `canonical repair` republishes a valid authorized current stage and restores
  corrupt hash-addressed files. Root/configuration conflicts may require explicit
  Git restoration; no automatic choice of a previous branch/root is made.
- Private staging and unreferenced immutable history are retained; automatic GC,
  background bit-rot auditing and a distinct Git-dirty boolean are not implemented.
  Proposals do bind the actual working-tree fingerprint and source version.

The supplied Definition of Done therefore remains open for those media, volume,
scale, cross-OS and real-model release gates. No PR URLs, registry publication or
physical hardware results are fabricated.

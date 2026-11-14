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

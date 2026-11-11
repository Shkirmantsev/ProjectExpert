# Verification and remaining release gates

Branch: feature/generate-init-project. Evidence dates: 2026-11-11–2026-11-12.
No result below is a claim of the full production target in the supplied V2 design.

## Executed

- Atomic source-state tests: committed output survives abrupt process exit;
  failed source buffers and conflicting payload transactions remain invisible;
  generation membership, metadata/pipeline compatibility, checksums, fences and
  bounded legacy migration are verified against real on-disk SQLite.
- Publication intent tests retain possibly published generations across the
  filesystem-snapshot/SQLite-pointer commit gap; GC never discards unresolved
  prepared publications. Parser degradation is counted separately from privacy
  knowledge-state policy.
- Public coordinator tests: model failure preserves completed parsing; changed,
  deleted and unsupported inputs cannot silently enter a complete candidate;
  legacy/resumable logical outputs, retrieval hashes and vector reuse match;
  prior runtime queries remain intact after a failed candidate; stale candidate
  publication is rejected. Existing readiness serving remains fail-closed.
- FTS artifact tests: restart after committed batches, standalone main-file copy
  without WAL, integrity/count verification, last-good preservation on promotion
  failure. Graph shard reuse and partial-file repair verified.
- Parsing/resource tests: Java native-failure fallback without AST claims,
  cp1252/BOM/binary handling, OOXML DTD/path/size defenses, presentation-order
  provenance, unsupported Office diagnostics, CPU/cgroup/memory admission and
  byte-identical serial/parallel canonical records.
- Embedding tests: batched text/segment requests, atomic put_many, invalid-vector
  rejection, reuse by complete profile contract and committed-batch progress.
  Query-only repeated Auto evidence requires fixed-probe numerical parity;
  evidence is invalidated after live controller generation changes.
- Real WAL backup/restore tests: private verified snapshots, interrupted
  multi-database restore journal/replay, reader contention, failure retention,
  managed workspace export/restore including the new state database.
- Strict TLS local fixture: imported CA succeeds, untrusted certificate fails.
  Deployment tests preserve compatible old images with no CA request; missing
  requested trust support fails with an upgrade diagnostic.
- Go workspace-agent tests pass. Compose overlays validate; Bash syntax checks
  pass. HTTP lifecycle tests show liveness ahead of retrieval readiness.
- Local benchmark harness: 9 actual runs, 30 generated Markdown sources and 180
  chunks; identical canonical generations in legacy, resumable serial and
  resumable parallel modes. Hashing embeddings only; no production speedup claim.
- `.venv/bin/python harness.py check`: PASS on frozen source, 1,930 tests run
  with 15 optional skips, including MCP tests, Wiki/OpenSpec and manifest gates.
  Final source changes were frozen for this run. Documentation/state-only
  finalization receives standalone manifest and whitespace verification.

## Not verified / not implemented at full production scope

- Native Windows PowerShell 5.1/7 and Rancher/Desktop end-to-end acceptance;
  regression scripts/workflows are added but were not executed on this Linux host.
- Complete redistributed offline assets, exact file/license inventory, published
  OCI digest, model/native extractor wiring and clean HF-denied model smoke.
  Default client model downloads remain unchanged; asset-lock.json blocks release.
- Packaged patched SQLite runtime proof and actual OS power-loss/full-disk matrix.
  Process exit and injected failures are useful evidence, not hardware power loss.
- Real EdkWmsXTotal timing, pinned llama b11515 batching and exact tokenizer checks,
  physical CPU/CUDA/Vulkan relevance and memory/VRAM acceptance.
- Real-model acceptance of opt-in PDF process workers and explicit multiendpoint
  dispatch; automatic artifact-file GC and all-stage hardware scheduling remain
  outside the verified rollout. Operator canonical GC is implemented with journal
  replay and retained active/previous/shared state.
- Automatic last-good UI serving during refresh/failure: accepted readiness still
  refuses cross-version evidence. Old artifacts/runtime are preserved, but that
  serving contract needs a separate verified adoption.

The rollout switches remain conservative. Current accepted specs/CURRENT are
not rewritten to imply these release requirements have been delivered.

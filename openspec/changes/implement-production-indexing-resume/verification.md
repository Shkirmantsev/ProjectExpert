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


## PR 22 CI follow-up — 2026-11-12

Windows job logs identified read-only `fsync` failure during FTS finalization,
Docker-only launcher fixtures entering managed-helper mode, and an intentional
native exit code leaking from a passing contract test. Repaired the responsible
handle mode and fixture boundaries without changing managed workspace defaults
or suppressing native error assertions. Launcher assertions now check the Docker
child environment while verifying that parent preferences remain unchanged.

The unit matrix timed out because the Actions Python wrapper re-entered the
entire suite in spawned children. A real spawned-process fixture reproduces the
failure in the exact workflow wrapper and passes with its new main guard.

CodeQL check 131003204592 reports insecure TLS versions in the local test server
at `tests/test_enterprise_ca_handshake.py`; its minimum is now explicitly TLS 1.2.
Strict trusted-root success and unknown-root rejection continue to pass.

Local verification: full harness PASS (1,932 tests, 15 optional skips), artifact
flush/spawn/deployment regressions PASS, and official checksum-verified portable
PowerShell 7.4.6 parser/mocked-launcher execution PASS on Linux. Native Windows
PowerShell 5.1/7 and new CodeQL execution are tracked through the repaired PR CI;
portable execution does not certify native Windows behavior.


Publishing this follow-up from the repair session is blocked: the configured Git
remote has no usable SSH authentication and the connected GitHub integration
returns HTTP 403 for Git tree creation. No remote branch update was performed.
The repair is committed locally for the owner to push before the native matrix
and CodeQL can certify it. Original unit logs confirm recursive suite execution
in spawned children and job cancellation; the guarded-runner regression passes.


## PR 22 second CI follow-up — 2026-11-12

Runs 43169268272 and 43169268308 exposed independent native Windows and real
GGUF admission failures after the first repair. CodeQL now passes remotely.

Windows byte-range locks deny reads through a second handle, including in the
same process. `exclusive_indexer` previously read byte zero before attempting
its lock, leaking PermissionError instead of the expected contention error.
It now acquires the kernel lock without protected-byte I/O; Windows supports
locking beyond EOF, so an empty lock file needs no initialization
([Microsoft CRT contract](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/locking?view=msvc-170)).
This also repairs PDF worker initialization, GC, backups and checkpoints through
the shared lock implementation. A simulated mandatory-lock regression reproduces
the previous failure on Linux, while native contention coverage stays enabled.

Portable tests now create mocks for absent POSIX APIs, simulate unavailable
Windows memory information, encode the Unicode legacy-cache fixture explicitly
as UTF-8, and close its inspection SQLite connection before directory cleanup.

The GGUF adapter previously rejected the 1,500-word real smoke document because
its UTF-8 byte upper bound exceeded the token budget. Ambiguous bounds now use
the pinned runtime `/tokenize` response with special tokens before admission.
Short inputs keep the existing no-round-trip packing path. Exact oversized
inputs and malformed tokenizer responses still fail explicitly; item and token
batch limits remain enforced. The real smoke corpus has not been weakened.

Verification: 98 focused tests PASS; full `harness.py check` PASS (1,936 tests,
15 optional skips); unchanged real GGUF CPU smoke PASS with verified downloaded
backbone/projector, 1,507-token document, pixel-sensitive image vectors and 512d
normalization. Manifest verification and diff whitespace checks PASS.
Native Windows 3.11/3.13 is NOT RUN locally; rerun PR CI after publishing these
commits. The prior Git SSH and integration write-access blocker remains; no push
was attempted during this repair. Original production rollout limits above
remain unchanged.


## PR 22 third CI follow-up — 2026-11-12

All four Windows jobs in run 43171898548 reached the same remaining failure:
`test_crashed_source_has_page_checkpoint_but_no_complete_source_output` raised
WinError 109 from `Connection.poll()` after its PDF worker intentionally exited.
The coordinator handled EOF/OSError from `recv()` but polling was outside that
boundary. Poll and receive now share the incomplete-result handling, preserving
normal bounded child cleanup, transient crash reporting and sibling processing.

A cross-platform regression uses actual spawned workers and pipes, reproducing
Windows broken-pipe polling at the first crashed worker's pipe. It fails with
the previous implementation and passes with the repair. Its assertions retain
the committed page checkpoint, absence of incomplete canonical output, sibling
success, successful recovery on the next run and empty spool cleanup.

Focused verification: 37 PDF/cache/GC/checkpoint tests PASS. No tests were skipped
or disabled to address the Windows failure. Native Windows execution remains a
PR CI verification step after publishing the local repair.

Final local verification: full `harness.py check` PASS (1,937 tests, 15 optional
skips, zero failures), artifact manifest PASS, and `git diff --check` PASS.
The existing repository publishing authentication limitation remains; this
session creates local commits for the owner to push. Original rollout limits
above are unchanged.

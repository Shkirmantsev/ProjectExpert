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


## Mandatory offline distribution remediation — 2026-11-12

The follow-up audit correctly identified that the previous optional asset pack
was not a self-contained default installation. The source now requires mandatory
asset seeding and local-only model consumers; it does not claim that a completed
licensed asset release has been published. Active accepted specs remain unchanged
pending actual release adoption; the proposed one-click-distribution delta records
the stricter contract.

Implemented the common pinned pack verifier/preflight, exact dependency-lock and
GGUF identities, Docling accurate-table configuration checks, local tokenizer and
native Torch routing, default no-download GGUF/Docling/Torch behavior, explicit
developer pulls, and pre-index rejection before canonical cache/lock mutations.
Normal setup verifies all pack inputs before generating keys/provisioning models.

Mandatory seed now precedes model-setup and production for every exported mode.
Seed/setup have no network. Native Windows obtains the full pack only through
immutable OCI extraction and verifies it before native planning/execution. Existing
native key/reuse/device policy remains. Standard TLS and registry trust remain
unchanged; no proxy or certificate-verification bypass was introduced.

The controlled assembler computes actual per-file hashes/provenance and leaves
unreviewed output blocked. An independently pinned reviewed manifest is necessary
for a publishable pack; no license approval or OCI identity is invented. A separate
candidate-publication workflow is gated by that review. Production and kit
promotion require the real reviewed inventory, immutable OCI digest, no-network
idempotent seeding and exact-production-image internal-network smoke with actual
OCR/table/figure/tokenizer/GGUF/image/Torch inference and restart. The previous
online-download smoke is removed from production promotion.

Fresh kits bake reviewed pins and show kit revision/application/asset identities.
Explicit --upgrade retains operator environment/data, backs up managed templates
and diagnoses missing/mismatched pins. platform-assets displays running image IDs
and verifies the independently pinned active pack. No operator volume was deleted.

Verification evidence: 70 focused tests PASS (2 optional skips); 19 PDF/offline
regressions PASS; portable PowerShell 7 parser/launcher and actual-script mocked
native extraction/fail-closed ordering PASS. Full harness first found an old test
relying on implicit online defaults; its explicit developer-download case now
retains pinned-revision assertions. Second run found the new Make target missing
from the primary public declaration; the implementation declaration was corrected
without weakening help coverage.

Release evidence still BLOCKED / NOT RUN: complete actual asset materialization,
independent per-file redistribution review, asset OCI publication, real egress-denied
production model acceptance, and native Windows/Rancher/Desktop/physical GPU matrix.
Upstream pinned revisions were verified via official HF API. Size observations:
selected HF files total 1,926,526,077 bytes, native archives 690,085,633 bytes,
plus extracted runtimes and approximately 865 MB of GGUF/projector. The controlled
assembler refused this host before downloading: approximately 4.4 GiB free is
below its 8 GiB minimum. No unrelated disk contents were deleted. Existing
repository write-authentication limitations remain. Default setup now fails clearly
when the reviewed pack/pins are absent; the fresh offline release is not yet usable.

Additional compatibility proof PASS: existing checksum-verified local GGUF cache
with the new default no-download setup, real pinned CPU inference, 1,507-token
document, pixel-sensitive image vectors and 512d normalization. This developer
local-cache check does not certify the complete mandatory production pack.

A final workspace-fixture migration was also necessary: copied release-kit sources
now include managed asset-release/inventory metadata, and syntax-only Compose
topology tests supply clearly synthetic pins without fetching any image. All
workspace regression assertions remain enabled and pass. The common lesson is
to migrate every isolated kit/config fixture alongside mandatory deployment
metadata, rather than injecting fake release pins into global test/runtime state.

Final source verification: `harness.py check` PASS (1,947 tests, 15 optional skips,
zero failures). Workspace fixtures PASS (4 tests); help/offline regression batch
PASS (18 tests). Workflow YAML, PowerShell contracts, artifact manifest and
whitespace checks PASS. Publication gates intentionally refuse the current
blocked inventory/release; no real asset image was built, published or activated.

## Completed local assembly and operator approval — 2026-11-12

This supersedes the earlier materialization/local-acceptance blockers above.
The final pack contains 82 pinned artifact files plus seven retained notice/review
files. Original artifact hashes and provenance are unchanged. The operator
explicitly approved the canonical license classifications and notices under the
requirement of no-fee enterprise use without company-size limits. The canonical
manifest is verified and independently pinned as
`f3bd07b7dc304c73d5166a447fd50280fdf5e69cb9de9f7075f3c354b0db2f25`.
The complete review and upstream notices are committed under
`distribution/assets/licenses/`.

Both actual images were built. Fresh-volume internal-network acceptance passed
against the final approved pack: real OCR, tables/figures, tokenizer, wide text,
pixel-sensitive image embeddings, native Torch, indexing, UI, MCP, dependency
checks, repository-owner writes and restart. It reproduced and fixed root-only
seed staging permissions and installed-wheel dependency-lock lookup. The locked
production backend build also removes obsolete core setuptools metadata before
copying the exact production backend and building without another resolution.

Full final `harness.py check`: PASS, 1,955 tests, 16 skips. Approved-asset focused
suite: PASS, 28 tests. Actual AMD integrated-GPU Vulkan wide-text/image inference
also passed with runtime-reported device selection and denied egress. PowerShell
7 launcher, native extraction and managed-container CUDA fallback contracts
passed locally; no host driver or toolkit was changed.

Registry publication and standard published-image acceptance remain NOT RUN.
No actual GHCR digest has been recorded, and the separate registry release remains
blocked. The owner will push these commits and handle publication; exact input
hash, image identities and publication steps are in `distribution/assets/README.md`.
Physical Windows GPU/Rancher/Desktop and broader durability/rollout gates remain
open; local contract tests do not certify them. Existing user services/volumes
were preserved, and only disposable fixture volumes and superseded build artifacts
were removed.

## PR 23 CI bootstrap follow-up

All five reported failures shared the unpublished asset-release gate. Production
and seeding jobs called `release_identity` while metadata was still blocked;
workspace Go tests passed, but its helper-contract job unnecessarily built the
release-gated deployment kit. Logs: jobs 131549258687, 131549096396,
131548404102, 131549096201 and 131548403868.

PR/source validation now explicitly prepares the operator-approved independently
pinned candidate, checking the lock and notice hashes before materialization.
Only an actual inspected local Docker image ID is passed to candidate offline
acceptance. The preparer refuses an existing raw-pack directory and removes only
its own successful assembly after the image build. Default/non-PR preparation
still requires the published immutable release. Source seeding cleanup also
checks volume existence so an earlier error does not cause a second cleanup error.

The real `deployment-kit-candidate` target built both cross-platform helpers;
their SHA-256 checks passed. Actual kit export, complete Compose configuration
and application-image fallback checks passed with the verified local pack, while
the kit retained blocked publication metadata. Building ordinary `deployment-kit`
still failed with the expected blocked-release error. No OCI digest or release
status was fabricated, and no candidate-kit publication path was added.

Verification: six candidate-preparation regressions PASS; the initial 32-test focused
CI/packaging/workspace tests PASS; workflow YAML and every Linux run-step Bash
syntax PASS; full `harness.py check` PASS (1,961 tests, 16 skips). The candidate
Docker build/export and strict-gate checks above are actual local execution.
Fresh controlled assembly on GitHub and remote job reruns remain pending owner
push; candidate-preparation subprocess orchestration is covered by the regression
suite, and the unchanged approved pack has the prior full real offline/restart
acceptance recorded above. Registry publication and physical Windows hardware
certification remain separate outstanding release gates.

## Production remediation follow-up — 2026-11-13

Baseline reconciled by HTTPS fetch: dev `7099677ffd049cbcfccafff68dabe81b195bd148`,
identical tree to starting local `1d69ead`. SSH retrieval failed authentication.
The [acceptance report](../../../docs/PRODUCTION_REMEDIATION_ACCEPTANCE.md) records
the source fixes, exact model/runtime identities, measured fixture outcomes and
remaining physical-platform/registry/performance gates.

- PASS: initial 42 focused tests, selective migration/CI diagnostics regressions,
  Linux Compose profile matrix and real TLS root/unknown-root/wrong-host handshake.
- PASS: changed-source fresh-volume egress-denied real OCR/table/figure/tokenizer,
  wide text/image/native Torch inference, optimized engine status, UI/MCP and restart.
  Dependency-reusing validation image: `sha256:1b23a4f0b5b0433e70ccc420e72dc0068a17bc334fd30ede54bc987f82025045`.
- PASS: actual pinned Gemma CPU/AMD Vulkan individual and combined numerical/top-k
  parity. Joint admission rejected slower combination. Exploratory document-fixture
  rates do not establish whole-pipeline gains. No new backend adapter is certified.
- PASS: first socket-enabled full harness test phase (1968 tests); final artifact
  verification initially failed because source hashes had not yet been regenerated.
- Environment limitation: sandbox-only test run could not bind local HTTP/TLS
  sockets. Repeated with local socket access instead of weakening/skipping tests.
- PASS: direct repaired host-cache CI route, root seeding twice with network none,
  ownership repair of only the isolated runner cache, then authenticated real CPU
  GGUF inference (1507-token document, actual pixel-sensitive images). A failed
  non-root source-image experiment exposed root-only original asset files; the
  workflow was corrected before completion and regression proof added.
- PASS: canonical production build and full repeated fresh-volume egress-denied
  real acceptance with image
  `sha256:72493341f0934201e297aa3c591d86c9d59cb1c8b8e9ddb41eb5a3b2ae7d249a`.
  Installed `pip check`, parser/import and license gates passed. RepoDigests remains
  empty: this is local image evidence, not publication.
- PASS: subsequent full test phase, 1970 tests; final manifest gate initially
  raced concurrent documentation edits, then hashes were refreshed and verified.
- PASS: final `python3 harness.py check`, 1970 tests / 16 skips, zero failures,
  final artifact manifest PASS. Wiki validation, strict OpenSpec validation
  (94 items), workflow YAML/Bash syntax, launcher ordering regression and
  `git diff --check` passed. Documentation-only final evidence updates were
  followed by manifest regeneration/verification.
- Pending: remote workflows, authenticated published asset digest/matching kit, independent
  installation, physical Windows/corporate-network and original large corpus.

Source defaults implement the supplied optimized target. Production promotion
remains blocked; accepted current specs were not silently rewritten or archived.

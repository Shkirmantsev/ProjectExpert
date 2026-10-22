# Production reconciliation status

Verification date: 2026-10-21. This records observed implementation and executed
checks against `ProjectExpert-production-semantic-search-branch-reconciliation-plan.md`.
The original implementation audit remains historical evidence. Unchecked items
in the active OpenSpec change are still outstanding acceptance conditions.

## Implemented corrections

| Audit gap | Correction |
|---|---|
| R1 incompatible Gemma loader | Pinned supported SentenceTransformers/Transformers closure; text-only Gemma configuration, immutable revisions, correct query/document prompts; real CPU inference for both models |
| R2 successful gate with failed probes | Strict production probes fail on load/inference failure; core checks explicitly use inventory-only mode |
| R3 synthetic PDF fallback | Production uses actual Docling converter and HybridChunker; source failures retain explicit diagnostics; synthetic mode requires explicit test opt-in |
| R4 core-only distribution | Separate core/production image targets and Compose profiles; exact CPU hash lock, installed-package resource lookup and source installation guide |
| R5 abstract version monitor | Portable content/HEAD/branch polling, serialized refresh, retry, administrative requests, shared published UI/MCP runtime and readiness checks |
| R6 indexing blocks HTTP startup | HTTP starts before background bootstrap; wizard uses cheap dependency discovery; retrieval remains unavailable until publication succeeds |
| R7 floating dependency closure | Linux x86_64 hash lock covering 113 dependency coordinates, compatible fresh CPython3.12 install and pip check |
| R8 nonexistent acceptance tests | Checklist names actual test modules; real model/PDF/native tests run separately from model-free contracts |
| R9 overstated completion | Checklist preserves unverified release/container/scenario requirements; this report distinguishes runtime proof from release approval |

Further defects found during acceptance were fixed: exact-identifier punctuation
is quoted for FTS; exact hits preserve canonical metadata; historical runtime
rows cannot restore removed graph nodes; native generations validate profile,
dimension, count, keys and sample queries; atomic snapshot bundles preserve the
previous coherent generation after process interruption. Invalid embeddings
are rejected before persistence.

PDF canonical structural units retain source anchors and stable IDs. Actual
model-aligned HybridChunker segments are disposable embedding inputs, with a
normalized mean vector per canonical chunk. Projection policy and segment text
participate in vector reuse hashes. Oversized vendor table output is re-split
and checked against the actual tokenizer budget; it never silently truncates.

## Executed evidence

- All 60 canonical project skills available through Codex discovery; skill
  synchronization check PASS. Claude/OpenCode retain four core skills and routed
  catalog mirrors.
- Wiki MCP search/get used for bounded project retrieval; independent stdio
  connection validated the actual repository root and indexed Markdown.
- Fresh locked production installation: 113 dependencies plus platform; import
  checks and dependency compatibility PASS. Wheel resources resolve outside the
  source checkout.
- Both pinned real embedding suites: 19 tests PASS without skipped inference.
- Strict production capability gate: six checks PASS, including actual Gemma
  512d/Qwen1024d inference, native USearch and real Docling imports.
- Native ANN seeded benchmark: 1,000 normalized64d vectors, 50 held-out queries,
  Recall@10 0.998 against exact cosine, required floor0.90. This synthetic ANN
  check does not certify semantic relevance at production scale.
- Native/snapshot/lifecycle regressions include real process interruption,
  corrupted index/metadata/key recovery without inference, model override and
  switch-back file reuse. Broad focused run: 111 tests PASS.
- Actual PDF inference: native table cells and chart assets, scanned OCR,
  mixed native/scanned pages, two-page tables and model-aligned header-preserving
  splits PASS. PDF→real Gemma→native USearch integration PASS with second-run
  vector reuse and unchanged source bytes.
- Actual100-page conversion PASS. Actual600-page conversion PASS in734.533s,
  38 windows, maximum16 pages/window, peak RSS2,235,056KiB (about2.13GiB).
- Real Gemma→Qwen→Gemma plus committed Git branch A→B→A, graph removal,
  UI/MCP equality and native-generation reuse: PASS. Two-model multilingual
  golden evaluation also PASS (two integrated tests,46.316s total). Nine queries
  over11 fixture documents cover English, German, Ukrainian, Russian, Java,
  business rules, protocol IDs and cross-language retrieval. Recall@5=0.889 for
  both; Recall@10=0.889/1.0; MRR=0.816/0.817. Exact protected evidence and
  context-evidence coverage are100%. [Full measured evidence](verification/production-runtime-2026-10-21.json)
  includes NDCG, per-query latency, process RSS and index sizes. This small
  fixture is a regression gate, not a production-corpus quality guarantee.
- Final combined real PDF suite: six tests PASS, no skips,211.955s. This
  includes OCR, mixed pages, tables,100-page conversion and real model indexing.
- Shared-runtime CLI evaluation and evaluation/standalone regressions:28 tests
  PASS. `eval-retrieval --target /path/to/repository --golden /path/to/golden.yaml
  --no-baseline` uses the same published runtime as UI/MCP.
- Final `python3 harness.py check`: PASS,1,429 unittest invocations. Thirteen
  optional integration cases skip in this core lane; the real model/PDF proofs
  above ran separately without skips. OpenSpec, Wiki, project-context MCP and
  artifact-manifest checks PASS. Full log: ignored
  `tmp/local/production-harness-check.log`.
- Final installed-wheel smoke from `/tmp`: actual site-packages import,
  installed model inventory/license resources and generic license gate PASS;
  `pip check` equivalent validated114 compatible installed packages.
- Disposable production test environment, PDF assets, uv cache and package
  build directory removed after validation. Disk free space: about17GiB.

## Release and portability limits

Follow [PRODUCTION_INSTALL.md](PRODUCTION_INSTALL.md) for the supported source
installation. Linux x86_64 CPU is the verified dependency target; other systems
need their own resolved lock and execution proof. Full model switching can use
several GiB of RAM; the two-model test process measured roughly7–9GiB peak RSS.
This is an acceptance-process measurement, not a minimum single-model requirement.

The ready-made production image is **not approved for publication**. Its license
gate intentionally blocks12 exact coordinates under the existing policy. See
[PRODUCTION_LICENSE_REVIEW.md](PRODUCTION_LICENSE_REVIEW.md) for bundled notices,
source-install versus binary-redistribution alternatives and an unapproved scoped
review proposal. No operator approval was fabricated and no blanket allowance
was added.

Actual production Docker build/start/restart and the newly wired remote CI tier
have not run. Source installation and static container tests are separate proof.
The broad15-scenario combined live-server matrix, dedicated branch-performance
metrics and complete air-gapped wheel-bundle deployment remain unverified; see
`openspec/changes/production-semantic-search-and-branch-reconciliation/tasks.md`.

Temporary validation environments and downloaded PDF test assets are disposable;
small proof logs stay under ignored `tmp/local/`. Production Hugging Face weights
and the project Wiki MCP environment are retained.


## 2026-10-22 portable OCI deployment follow-up

Implemented a standalone GHCR kit with Compose, product Make targets, defaults,
and Linux/PowerShell launchers. Pushes/merges to dev, development and main build
and smoke-test the runtime, then publish it and a digest-bound kit with commit
and branch tags. PRs test without publishing. There is no automatic tag expiry.
The source remains in Git after merge; registry owner deletion is still possible.

The operator accepted the exact 12-coordinate production dependency review.
The 113-coordinate closure passes its hash-bound gate; this does not authorize
future dependency changes. The container trusts only its mounted /repo for Git
ownership checks. The diagnostic core stays explicitly hashing/flat.

CPU is the default. Optional pinned Gemma/Qwen GGUF Vulkan/CUDA runtimes run as Linux
sidecars or an automatically installed native Windows service. A separate vector
profile prevents reuse of incompatible PyTorch/GGUF vectors. Windows native
assets have checksums, bearer authentication, device probing and a guarded stop
script. Physical device support is not inferred from configuration validation.

Gemma vision is enabled for real text/image embeddings, including repository
images and extracted PDF figures; image bytes participate in vector invalidation.
Audio/video ingestion is not exposed. Gemma also has a GGUF text/image GPU
option with its pinned projector; Docling remains CPU-based. Pinned Docling layout/table/OCR assets download during
setup before readiness; selected embedding weights also download automatically.

Executed evidence:

- PASS: production Linux image build with the approved closure; automatic Qwen
  download, real indexing/search, readiness, UI/MCP, pip check and restart.
- PASS: actual Gemma image inference inside the production container using
  current mounted source: 512 dimensions, unit norm, text-image profile.
- PASS: pinned Qwen GGUF download and real authenticated llama.cpp inference
  from the Vulkan image running on CPU: 1024 dimensions and unit norm.
- PASS: clean Docling layout/table/OCR asset preparation in the container.
- PASS: final rebuilt production image startup, real search and restart with
  cached embeddings and Docling assets; real scanned-PDF OCR and PDF/Gemma
  retrieval (2 container tests, 38.654 seconds).
- PASS: full `python3 harness.py check`: 1,442 test invocations, 13 explicit
  optional skips. Separate real inference checks above cover selected skips.
- PASS: CPU/Vulkan/CUDA Compose configuration validation, focused adapter and
  deployment tests, and image-content cache invalidation regression.
- PASS: deployment kit build and export/preservation (initial and expanded kit).
- NOT RUN: physical CUDA/Vulkan inference (no devices exposed), Windows Docker
  Desktop/native runtime, and remote GitHub workflow/GHCR publication.

The local changes are not a published release. Hardware and remote checks remain
required before claiming all six deployment goals are fully verified. Final logs are retained under ignored `tmp/local/portable-oci-verification/`;
the task checkpoint records the remaining verification boundary.


### Gemma GPU and explicit CPU extension

The kit now preserves both model and backend selection. `gemma` with `vulkan`
or `cuda` selects `gemma-gguf` and automatically prepares the Q8_0 model plus
multimodal projector. `qwen` with `cpu` keeps the default native CPU path. Both
GGUF formats can also run on CPU through explicit `gemma-gguf`/`qwen-gguf`
selection. The Gemma conversion's source revision matches the existing pinned
Google model. No Python dependency approval scope was expanded.

PASS: all 12 model/backend Compose combinations; real Gemma GGUF text and image
inference with pixel-sensitive output and normalized 512d vectors; full Compose
model setup, sidecar health, app readiness and image retrieval; rebuilt runtime
and kit. A deployment test found stale persisted model status after an environment
switch; effective environment settings are now resolved before source fingerprinting
and persisted with the actual selected model/device. The final rebuilt image
passed real Qwen CPU search and stable readiness across three monitor intervals.
The final full harness passed 1,446 test invocations with 13 optional skips.

Physical Vulkan/CUDA devices and Windows execution remain unavailable here.
The real GGUF tests use the pinned GPU-capable runtime in CPU mode and do not
claim physical GPU acceleration. Publishing remains pending merge and remote CI.

Validation cleanup removed task-created duplicate Docker layers, the temporary
dependency-install cache, obsolete test images and downloaded test model/Docling
copies. Free disk space recovered from about 809 MiB at peak validation usage to
11 GiB. Existing user model caches and the final tested runtime/kit images were
preserved; no broad Docker or user-cache prune was performed.

### PR 10 CI portability corrections

The initial GitHub runs exposed differences hidden by the locally installed
optional packages and Linux file semantics. Corrections preserve configured ANN
dimensions after deleting an absent/final vector, close owned SQLite handles,
and make tokenizer/stub tests independent of installed models. Windows path and
UTF-8 assertions are platform-aware. POSIX shell fixtures run on Linux; native
Windows launcher contracts remain a separate required job. The PowerShell
contract clears the deliberately injected failure exit code after all assertions
succeed, so the runner does not misreport PASS as failure.

The two skipped OCI jobs depended on the failed Windows launcher job; their
prerequisite gates remain intact. A new remote run is required to confirm these
fixes on both Windows Python versions and allow container verification to run.

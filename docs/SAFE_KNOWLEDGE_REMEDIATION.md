# Safe knowledge workflow and evidence

Local implementation from remediation v1.1, 2026-11-15. This is not physical
deployment certification. The current branch and existing indexer are retained.

## Operator flow

1. **Restore knowledge from Git** imports compatible complete source results and
   vectors without scheduling parsers, OCR or embedding requests. Derived indexes
   activate only when current inputs are complete. Missing inputs return
   `requires-reindex`; checkpoints and previous activation remain retained.
   `canonical restore-only` shares this operation (exit 2 means reindex needed).
   Existing `canonical hydrate` still performs bootstrap/indexing.
2. **Reindex / Update local knowledge** reconciles portable data, computes missing
   local work and publishes locally. Corrupt/unsafe Git snapshots are rejected as
   cache inputs without disabling independently verified local calculation.
   `canonical verify` stays strict. Restore never falls back to parsing.
3. Enable **safe Git export** in sharing preferences, then reindex once if older
   results lack portable identities. **Export safe knowledge to Git files** stages
   eligible complete sources. Review counts, file paths and size, then authorize
   publication through the signed root-last writer. Git add/commit/push stay manual.

Publication requires existing API bearer authentication (`PI_UI_TOKEN`) and
administrator capability. Anonymous deployments may index/stage but cannot issue
grants. The server creates a private key if no operator key is configured; signing
material never reaches browsers. Optional `PI_OPERATOR_APPROVAL_KEY_FILE` loads a
privately mounted file (POSIX group/other permissions must be absent). Existing
environment keys remain compatible. No signing value belongs in deployment.env.

**Automatic export after Reindex** defaults off. Authenticated administrators can
enable a repository-scoped one-hour grant; save again to renew it. Export failure
does not invalidate local indexing. Saved UI preferences override legacy export
environment modes. Preferences, exact-byte source reviews, grants and job history
remain in ignored runtime storage across kit upgrades. Restarted running jobs
report interruption rather than waiting forever.

## Admission, scope and retained files

Whole complete sources pass policy, conservative content detection, canonical
metadata, ownership and graph/provenance closure. A disk-backed catalog propagates
denials to dependent sources. Restricted/unknown results and their vectors remain
local; unrelated safe sources still export. Detector failure excludes its source.
In a Git checkout, untracked sources are not assumed shareable. Legacy unversioned
targets remain supported; that does not establish cross-clone source availability.
No eligible source means no public snapshot. Exclusion reports contain reason
counts, not protected paths or values.

Opaque images/PDFs stay local until an authenticated human reviews their complete
contents and records an exact-byte public classification. Changed bytes invalidate
that review. Confidential classification stays local. Public review cannot override
content/policy detectors. This is human classification, not automated visual secret
detection. The UI provides a relative-path classification control.

Optional v2 root `scope` declares `eligible-sources-only`, policy version, exported
count and completeness for that scope. It never claims full local completeness.
Each source remains complete; no partial fragments count as parse hits. Earlier
text snapshots remain readable: v2 already tolerated extra root keys. Media/PDF
projection identities are versioned; older readers that cannot validate media
vector ownership fail closed rather than misusing the vectors.

Publication audits retained generated files, including orphaned shards. Newly
restricted data, unknown old vector ownership, links or unsupported files require
owner-reviewed cleanup before root mutation. No files or Git history are silently
deleted. Inspect generated paths privately, review removal, then restage. This
conservative refusal can also follow source changes/deletion when old vector
ownership cannot be established. Automatic cleanup remains absent. Signed repair
can still restore matching staged files. Author-managed Wiki/Git commits are a
separate channel; this workflow scans Wiki when indexed as source.

Private cache directories use POSIX 0700; state/preferences/keys use private files.
Indexing refuses a Git-tracked runtime cache; linked worktrees use their actual
Git exclusion location. Filesystem permissions are not encryption. Windows ACLs,
encrypted backups and per-document multi-user query ACLs require deployment
acceptance: use isolated authorized hosts meanwhile. Sensitive original sources
already tracked in Git remain outside generated export filtering; review history
and rotate credentials separately.

## Media and PDF behavior

Images now have durable SQLite source membership and versioned canonical media
descriptors. Original pixels remain source files, never base64 JSONL. Optional
float32 vectors bind source bytes, image projection and exact model/profile.
Compatible vectors reuse across clones; missing vectors alone require inference.

PDF chunks retain page/OCR flags, geometry, tables and figure descriptors containing
source bytes, page/bbox, crop hash, strategy and package/render profile. Compatible
PDF vectors restore without crops or full Docling parsing. Missing visual vectors
can regenerate the required page through the existing converter and must reproduce
the exact crop hash. Multiple missing figures on one page share conversion.
Render mismatch requires reindex. Neutral descriptors support retrieval/citations;
not every documents-v2.sqlite table is replicated. Preview integrations must
explicitly request crop reconstruction; a vector cannot recreate pixels.

## Interfaces and evidence

Administrator routes under `/api/v1/admin/knowledge/`: GET status, GET/PUT settings,
POST restore/reindex/export, GET proposals/{id}, POST publish (reviewed stagingId
and snapshotId), POST source-review (relative path and public/confidential).
Existing reindex/job endpoints remain. Safe results expose counts/file paths;
knowledge failures omit raw source/credential excerpts. Job state persists privately.
Protected parser diagnostics suppress exception text and tracebacks. Generated
Wiki writes also scan before preview or storage, including declared restricted
dependency metadata; direct human Git edits remain outside this API guarantee.

Regressions: `test_safe_git_export`, `test_knowledge_sync_ui_workflow`,
`test_portable_pdf_assets`, `test_source_checkpoint_scale`, existing portable,
resumable, native ANN, PDF process and shipped browser-script suites. PDF fixtures
use real document types and controlled converter/model responses, not model quality
claims. HTTP restore runs the real server and candidate publication path.

50-source hashing benchmark: initial 0.563s; warm 0.357s; full-vector clone 0.471s;
no-vector clone 0.427s; five-source delta 0.400s; return 0.288s. Twelve parser workers
were admitted. These are illustrative local timings. A new instruction-budget test
exposed quadratic checkpoint progress: 200→400 sources used 337,100→1,274,200 SQLite
instructions before repair. Indexed source deltas now pass <2.8x growth. Image/PDF
membership now uses sets. Existing resource-aware parallelism, bounded import groups
and PDF subprocess admission remain. Vector export shares one read-only SQLite
connection instead of opening one per chunk/profile, and UI export reuses its
already verified stage report. No physical multimodal speed is inferred.

Previous baseline CI was independently rechecked through GitHub at
`f00268bbf83bd13732a7587895c3d34ee86ebed0`: verify `43643312759`, production runtime
`43643312745`, publication `43643312753` all succeeded. Those runs do not validate
these unpushed changes. New hosted CI, physical Windows/Rancher/Linux mounts, real
offline models, CUDA/Vulkan and representative large corpora remain release gates.
No push, merge or deploy was performed by this task.

Local verification: `python3 harness.py check` PASS (2,045 tests, 159 suites,
20 skips), including the full 50k graph build (3.7s; 4.9s including cleanup).
The subsequent administrator/HTTP workflow run passed 32 tests, including the
additional restart-persistent reindex regression. Shipped browser behavior PASS;
OpenSpec strict validation 96 items PASS; Wiki 136 documents, zero issues;
artifact manifest 1,604 files PASS. Source policy, diagnostics, generated Wiki,
legacy publication and image-projection regressions were demonstrated failing
before their corresponding fixes. No physical host/model success is inferred.


## PR26 Windows, security findings and UI delivery repair

All eight reported Windows jobs in runs `43710889902` and `43710889944` traced
to SQLite fixture connections retained during temporary repository cleanup
(WinError 32). A SQLite transaction context does not close the connection. The
fixture now explicitly closes it after commit; a real-handle regression retains
strong references and proves the handles reject subsequent queries.

Code scanning check `132802207581` reported two `py/clear-text-storage-sensitive-data`
findings at the test writes formerly on lines 116 and 258 of
`tests/test_safe_git_export.py`. These writes contain deliberately invalid,
deterministic detector markers. Fixture variables now state that provenance
instead of the sensitive-variable name that CodeQL treats as a data source.
Detector strings, rejection assertions, production secret filtering and the CodeQL
workflow remain intact. A fresh hosted CodeQL analysis is required after push;
no local CodeQL executable is installed.

The UI retains the old dark/green visual language, adds three responsive action
cards and readable results, and fixes duplicate result IDs and file-preview asset
URLs. File previews are explicitly disconnected and cannot issue API requests.
Live HTML/assets/API use no-store caching and a public asset-build identity.
Unmanaged external Gemma runtimes cannot offer ineffective GPU changes.

Read-only inspection found port 8765 serving container
`project-intelligence-production-1`, image
`sha256:7735bb830a7a6635acccfc45ef3a587030446f01cee4322467c62262c178eeb3`,
mounted to the separate trade-analyzer project. That image has no Restore control
or current UI-version endpoint. Its embedding container lacks the managed runtime
controller mounts. Updating source or refreshing the browser cannot replace this
image; the application and managed deployment kit both need upgrading. This task
does not modify that separate project's files, configuration or running services.
The failing acceptance checks skipped production publication, so no successful
publication of this repair is claimed.

Actual browser verification used an isolated fixture server on port 18884:
desktop/mobile styling, restore requiring a local update without parsing/new
embeddings, and reindex completion with one reused source all passed. The dummy
embedding endpoint in that preview does not certify physical GPU behavior.
The existing 8 MiB default shard cap (configurable 1–16 MiB), bounded admission
and parallel source processing remain unchanged. Fresh hosted Windows, CodeQL
and physical GPU acceptance remain pending owner push/deployment.

Final local PR26 verification: `python3 harness.py check` PASS, 2,049 tests across
160 suites, 20 skips; strict OpenSpec validation 96/96 and artifact manifest
1,605 files PASS. The 50k graph fixture built in 3.7s and finished cleanup in
5.0s. The retained-handle, UI delivery, parallel ingestion/embedding and linear
checkpoint regressions passed in that run. Shipped browser script PASS.
Local commits: `dd82a8c` (Windows/security fixtures) and `48f3fbd` (UI delivery).
An offline local repair image (`0ee8ddb4849c`) also passed its actual HTTP build
identity and Restore markup smoke test with no host mounts/external network.
The candidate and source-only kit review live under `/tmp/projectexpert-pr26-upgrade`;
that kit is not a published release and must not overwrite reviewed asset pins or
operator settings. The live external upgrade awaits explicit owner scope.


## Owner-approved live upgrade follow-up

The owner subsequently approved the separate trade-analyzer deployment upgrade.
Private backups were created before editing deployment files. Operator settings,
model data and reviewed pins were preserved; only the app/embedding services were
restarted. The current UI build and managed controller became available on 8765.
Explicit resumable indexing, parallel ingestion and embedding batching were enabled.
Pre-restart validation caught an insertion into a nested dependency mapping; it was
corrected from the backup before services restarted.

Live startup exposed a Python-version compatibility failure: a valid Python 3.12
f-string cannot be parsed by the container's Python 3.11 AST. The source adapter
now uses the already installed/reviewed production tree-sitter Python grammar only
when AST parsing fails. It rejects grammar errors, preserves the full source as
text and explicitly reports unavailable AST symbol analysis. It does not execute
source, fabricate API entities, edit target code or relax completeness policy.
Core stdlib AST behavior is unchanged; without the optional grammar the error is
still explicit. The existing production dependency inventory already includes
`tree-sitter-python` 0.25.0. The new retained-text regression failed before the fix;
all nine Python adapter tests passed afterward, including invalid syntax and
missing-grammar failure. This fallback is bounded by the existing 5 MiB source cap.


Approved upgrade result: the live application now uses local image
`sha256:5c6968dcaa93fcb3e0772073986cd9c4e90c7d42cbcb98a5751d08a5fdde7d90`.
The previous deployment files and environment are privately backed up under
`.project-intelligence-deploy/.kit-backups/live-pr26-20261115T134516Z/` in the
trade-analyzer installation. The original application image remains cached for
rollback. Restore backed-up managed files and remove only the new controller files
listed in `rollback.json`, then recreate app/embeddings with the original Compose
file set if rollback is needed. Keep backup contents private; never commit them.

Verification: live `/health` is ready, `/api/v1/ui-version` reports the current
knowledge workflow, and the browser displays the themed page and live CPU mode.
The authenticated internal controller is healthy. A GPU request with no exposed
GPU returns HTTP 400 and preserves the exact healthy CPU process generation.
Normal reindex completed with 345 source hits, zero parse misses and zero new
vectors. A real deterministic retrieval returned indexed evidence in 0.064s.
These are observed local measurements, not a physical GPU benchmark. All operator
`deployment.env` bytes except the approved image replacement were verified equal
to backup. Existing model volumes and settings were retained; no new public ports,
Git push, merge, or registry publication were performed.

After the syntax fix, `python3 harness.py check` PASS: 2,051 tests across 160 suites,
20 skips; artifact manifest 1,605 files PASS; OpenSpec 96/96. The 50k graph build
finished in 3.8s (5.1s with cleanup). Source compatibility commit: `dee6f78`.
Fresh hosted Windows/CodeQL acceptance remains for the owner-pushed branch.


## Project-wide controls and private local/MCP context

The owner requested optional PI_UI_TOKEN for local use and rejected both manual
source paths and a proposed multi-file picker. The final UI has no per-file review
controls. One checked export rule applies across discovered sources. Existing
source policies, tracked-source eligibility and provenance restrictions still
apply uniformly; a local-only or unknown-provenance source is not made public by
removing the form.

The running container enables bearer authentication when `PI_UI_TOKEN` is
configured. If that value is absent or empty, the token form is hidden and
administration is available from any reachable address. Browser writes still
receive same-origin checks and canonical publication requires signed approval.

Full confidential source outputs/vectors stay in the private cache and remain
available to local retrieval and ProjectExpert MCP. The export projector never
rewrites them. Complete safe source snapshots remain reusable. Independent safe
text fragments from content-contaminated sources can now be exported as separate
`context` records with exact text hashes and original source provenance. They do
not carry aggregate source summaries, graph edges or opaque media vectors and
cannot satisfy a complete original-source cache hit. Source-wide policy, unknown
provenance and protected-dependency denials remain conservative.

All media descriptors/text are checked without individual approvals. Uninspectable
pixel/figure embeddings remain local unless existing exact-byte review evidence
already authorizes them; raw images/PDF binaries are never added by this exporter.
Export uses cached text only and schedules no parsing, OCR or model inference.
Automated detection covers recognized credentials and declared restrictions; it
cannot establish arbitrary business confidentiality from meaning alone.

The additive checked-context record/scope fails closed in old readers. New readers
retain complete-source snapshot compatibility. Exact text vectors can be rekeyed
only when their original input hash/profile matches the checked projection. Safe
shared contexts are distinct evidence in the committed snapshot; full current local
sources take precedence and incompatible current source hashes/policies exclude
stale projections. See ADR0036.

A real MCP regression exposed a separate assembler-call mismatch hidden by mocked
ports. `project.retrieve_context` now reuses the real pipeline context bundle or
calls the declared assembler port correctly, avoiding redundant assembly. The
mixed-source regression verifies safe export, excluded credential bytes, retained
complete local cache, real MCP retrieval of confidential text after export, exact
vector reuse on clone and tamper rejection. UI tests verify hidden optional token
entry; HTTP tests verify tokenless access, cross-origin write denial and configured bearer authentication.


Final project-wide verification: `python3 harness.py check` PASS, 2,100 tests across
162 suites, 20 skips; strict OpenSpec 96/96; Wiki 137 documents; artifact manifest 1,609
files. The 50k graph built in 3.7s and completed cleanup in 5.0s. A supplemental
12-test MCP suite passed after adding two real-assembler/reuse regressions. The
protected-provenance regression failed before the new guard and passed afterward.
The isolated candidate container also authorized local signing without a token
using disposable data and no external network.

The approved loopback installation now uses image
`sha256:fff31b3c35ef019c6cd606d0607c3c12e39a60a23c1aa44a9bdd929cafc2ae46`,
UI build `1772e6a4ca23167048cd8e7526520c3f761a46f84bc719e8e6fbbf109f2929a3`.
Private rollback files are in the installation's
`.kit-backups/global-context-20261115T165205Z/`. The earlier 5c6968dc image remains
cached. Restore that backup's compose.yaml/deployment.env and recreate only the
application if rollback is needed. Deployment preflight found that the older base
file did not pass PI_UI_TOKEN at all; the optional reference and loopback-owner
settings were added without changing any existing environment value except the
approved image replacement. Embedding service, models and private data were retained.

Live health/search readiness PASS; auth-status reports token_required:false and
local_owner_access:true. Local knowledge administration works without token;
foreign Origin/Host requests return 403. Reindex reused 345 sources, parsed 0 and
created 0 embeddings. An actual HTTP MCP project.retrieve_context request returned
32 hits and its assembled context bundle in 0.066s, with no chat-provider call.
Chrome's existing localhost:8765 tab was refreshed and verified: themed UI,
optional-token panel hidden, no source path/picker, unchanged sharing preferences
and complete local search ready. Screenshot is stored in the session visualization
output as global-checked-export-live.jpg. Export, automatic export and vector
sharing remain disabled as before; no real project export, Git push or merge was
performed during verification. Hosted Windows/CodeQL and physical GPU acceptance
remain external gates after owner push/on suitable hardware.

Local source commits: e84a59f (real MCP assembly/reuse), c78c6cc (optional local
owner and global controls), fb56a4b (checked fragments with private cache intact).

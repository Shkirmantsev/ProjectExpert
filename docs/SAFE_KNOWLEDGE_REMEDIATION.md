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

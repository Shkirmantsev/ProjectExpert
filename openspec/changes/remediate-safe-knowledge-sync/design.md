# Design

Reuse the resumable indexer with an explicit restore-only mode. Imported or local
compatible source outputs must cover the current inventory before derived index
building. Missing vectors refuse activation without calling the model. No source
parser, OCR or embedding fallback is permitted. Readiness distinguishes imported
SQLite data from a published query generation.

Export admission uses complete sources, never edited canonical payloads. A
disk-backed catalog tracks owners and references; denials propagate through shared
payloads and dependencies before any record reaches the stage. Scan source policy,
source bytes, canonical metadata and derived text. Diagnostics expose reason counts,
never excluded names or values. This conservative filter cannot prove arbitrary
secret detection or secure multi-user retrieval; retain isolated-host deployment
limits. Old generated files require a separate safety check before publication.

Use additive root scope metadata: v2 readers already tolerate extra root keys and
each included source remains complete. Media descriptors have versioned projection
identities; runtime absolute paths remain local. Exact model/profile/content and
projection hashes bind vectors. PDF asset reconstruction must verify source bytes
and rendering identities; missing support reports requires-reindex, never readiness.

UI administrator requests share existing job execution and HMAC publisher. Settings
live in ignored runtime storage. The server holds signing material; the browser
receives no key. Export approval cannot override admission. Default auto-export is
off. Serialize restore/reindex/publication with existing locks and source fences.


## PR26 delivery corrections

Keep the existing adaptive dark/green theme and group Restore, Reindex and Export
in responsive action cards with a dedicated, unique result target. Relative static
assets support file previews; preview mode disables controls and makes no API
calls. A public build fingerprint identifies delivered assets without exposing
operator configuration. API and static responses prohibit stale browser caching.
External Gemma device selection requires a managed runtime controller; otherwise
the UI explains the host upgrade rather than offering an ineffective selector.
These changes do not change source admission, parallel workers or shard limits.

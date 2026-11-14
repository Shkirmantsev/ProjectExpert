# Design

Use source-scoped immutable payloads from the published generation. Keep runtime.db,
indexing-state.sqlite and portable text distinct. Stage in ignored private cache;
SQLite spools bound cross-corpus sorting and verification. JSONL records are typed
source, payload and vector envelopes. Source records bind relative POSIX source
ID, source bytes, portable pipeline/metadata keys and complete summary membership.
Payload addresses are SHA256 of the original canonical bytes; text preserves
those bytes. Vector records omit creation time and carry exact profile provenance.

Shard files and recursive manifest pages are content addressed and immutable;
the sole mutable manifests/portable-v2.json pointer is replaced last. Root identity
is SHA256 of canonical root body without snapshotId. All files default to 8 MiB,
with bounded total bytes/files and explicit oversize-record failure. A separate
8 MiB cap and atomic replacement protect the legacy graph writer.

Verified readers spool all records and validate complete membership before any
import. Import is inside the existing exclusive indexer and per-source fenced
transactions. Candidate FTS/graph/dense publication remains caller-owned. Incompatible
sources are misses; corrupt snapshots fail closed. Vectors enter the normal store
before normal profile validation. Historical outputs remain available for branches.

Export is off by default; PI_PORTABLE_EXPORT=review enables portable identity and
post-publication private proposals. Presence of a v2 root also enables identity and
import. Full vectors require an explicit option. Publication requires signed scope
for snapshotId, current source version and published generation, plus existing OKF
and license gates. Approved-auto is deferred until a persistent scoped capability
exists; no string token shortcut. Managed volume write-back remains owned by its
existing synchronizer; do not add an independent volume-to-host writer.

Security: constrain all paths without symlinks/hardlinks, disallow traversal,
Windows reserved/colliding source paths, and reject unknown source classifications.
Only repository sources outside tmp/local with policy empty or SNAPSHOT qualify;
REFERENCE and LOCAL_ONLY never export source text. Shared payloads owned by a denied
source are excluded by denying their whole source result (no partial membership).
Reject machine-bound payloads and credential patterns rather than strip them.

Limit: import/export buffers one source output, as the existing pipeline does;
oversize summaries/records fail explicitly. Corpus-level sorting is disk-backed.

# Indexing state backup and recovery

These commands manage **derived runtime state**. They never export, delete or
rewrite canonical project source or `project-knowledge/`. Run the script from
the repository root using the same Python/runtime version as the deployment:

```bash
python scripts/indexing_state.py --cache /path/to/.project-intelligence-cache status
python scripts/indexing_state.py --cache /path/to/.project-intelligence-cache backup /private/backups/unique-backup
python scripts/indexing_state.py --cache /path/to/.project-intelligence-cache verify /private/backups/unique-backup
```

Backup acquires the same exclusive OS indexer lock as indexing. If another
builder owns it, the operation fails; stop indexing first and retry. A backup
copies the following files when present through the **SQLite backup API**, so
committed WAL frames are included without raw-copying a live main database:

- `indexing-state.sqlite`
- `indexes/embeddings.sqlite`
- `documents-v2.sqlite`

Every closed backup database passes `quick_check` and `integrity_check`; the
private manifest records its SHA-256 and size. Verification checks these again.
Backups contain source-derived text/vectors and should be treated as private
project data. On POSIX, newly created backup/attempt directories use mode 0700,
and database/manifest files use 0600. On Windows, place them under an NTFS
location with an appropriate private inherited ACL; POSIX mode bits alone do
not establish Windows ACL isolation. Select a new directory for every backup;
existing backup destinations are never overwritten. A failed backup directory
is retained without a successful manifest, rather than being reported valid.

## Restore with serving stopped

Stop the serving application and all other processes that may own these
SQLite files before restoring. The indexer lock excludes builders; it does
**not** evict query connections, external PDF workers or unrelated database
clients. A busy WAL checkpoint fails the operation instead of replacing files.
A live process may hold connections without a busy checkpoint, so stop it even
when the tool does not report busy.

```bash
python scripts/indexing_state.py --cache /path/to/.project-intelligence-cache restore /private/backups/unique-backup
```

Restore verifies the input backup, acquires the indexer lock, creates a private
`pre-restore-<id>/` backup of current derived databases, and writes/fsyncs
`restore-in-progress.json` **before any replacement**. It creates standalone
staged files and checkpoints/closes existing SQLite files. Existing main files
and any WAL/SHM/rollback-journal sidecars are moved into a private attempt
subdirectory, then staged files replace the main paths. Displaced files and the
pre-restore snapshot remain available; the tool does not delete them or run GC.
Each replacement is durable, but a multi-database restore is not one atomic
filesystem transaction. The journal prevents indexing from using a partial set.
Only after every restored database verifies does restore remove the journal.
Start the application with the matching runtime/configuration; the coordinator
can rebuild generated retrieval artifacts from the restored durable state.

## Interrupted restore

Keep the application stopped. Do not delete the journal or SQLite sidecars.
Inspect `status`; then resume the original operation:

```bash
python scripts/indexing_state.py --cache /path/to/.project-intelligence-cache restore --resume
```

Resume verifies the original backup manifest's pinned SHA-256 and its database
checksums again, verifies the retained pre-restore backup, acquires the same
exclusive lock, and replays the complete restore into fresh attempt directories.
Replaying handles interruption between moving an old main file and promoting a
new one. Previously displaced files remain untouched. Ordinary restore and new
backup commands fail while the journal exists. Index startup fails closed while
this marker exists; it must be cleared by successful restore completion.

If the original backup is missing or damaged, recover its exact verified bytes
from backup storage. Resume intentionally rejects a changed manifest. If those
bytes cannot be recovered, preserve the interrupted cache/journal and use the
retained verified pre-restore snapshot to restore into a **new empty cache**:

```bash
python scripts/indexing_state.py --cache /private/recovery/new-cache restore /old/cache/pre-restore-ID
```

Configure the stopped application to use that recovered cache and matching
runtime, or perform a clean derived-state rebuild from canonical sources in a
new cache. Keep the interrupted directory until recovery is independently
verified. Restore does not certify cross-version schema compatibility, restore
an entire Docker volume, or promote a saved ANN/exact index snapshot.

## Canonical generation cleanup

Stop serving readers first. Plan without committing any deletion:

```bash
python scripts/indexing_state.py --cache /path/to/.project-intelligence-cache gc
```

`gc --apply` performs journaled reachability cleanup in one FULL-synchronous
transaction. The durable `active_job` and `previous_job` pointers are authoritative;
the latest two published jobs, newest compatible ready candidates, and unexpired
compatible attempts are also retained. Shared payloads remain until no retained
source version references them. Prepared publication intents are retained without
TTL expiry because the snapshot may already have committed before an audit-pointer
failure; reconcile them against the published snapshot before any manual cleanup. Unknown generation membership is conservatively
kept. For pre-pointer state only, explicitly supply `--active-job` and optionally
`--previous-job`; conflicting identities fail closed.

After interruption, keep readers stopped and run `gc --apply --resume`.
`gc-in-progress.json` and a committed operation record make replay idempotent;
ordinary indexing/checkpoint export refuses an unfinished operation. GC reports
logical reusable SQLite pages, not physical disk reclamation; it never runs
VACUUM or deletes artifact files. Quota/free-space options report remaining
violations without evicting active data. Artifact-file GC remains disabled until
reader lifetime and complete artifact reachability can be proven.

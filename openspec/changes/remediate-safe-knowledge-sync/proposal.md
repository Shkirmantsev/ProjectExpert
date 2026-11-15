# Safe knowledge workflow remediation

## Why
The supplied remediation v1.1 identifies confirmed gaps on the current branch:
hydrate runs the general indexer, denied payloads abort export, image results lack
durable membership, and the UI has no restore/export workflow. This change builds
on implement-git-portable-canonical-sync rather than replacing it.

## What changes
Add strict restore-only orchestration, source-level safe export admission and
closure, explicit coverage, durable media descriptors, administrative jobs and
private project preferences. Keep signed root-last publication and local indexing
independent of export. Extend deployment configuration and regression evidence.

## Compatibility
Keep legacy commands and readers. Optional exportable-scope metadata does not
change complete source-result semantics; no partial source cache hits. Existing
SQLite results and earlier active generations remain retained. No Git staging,
commit, push or destructive migration occurs in product workflows.

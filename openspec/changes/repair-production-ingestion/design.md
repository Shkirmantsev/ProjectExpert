# Design

Use a small immutable standard-library decoding policy loaded once per indexing job from private cache/config/source-encodings.json. Strict UTF/BOM precedence, reviewed fallback codecs only; conflicting matching rules fail closed. Match repository-relative paths, persist only effective codec identity in pipeline keys, never private review text. Existing portable importer already compares pipeline identities. Preserve parser parallel workers and original byte hashes.

Typed incomplete-ingestion failures drive the existing monitor, with private atomic failed-candidate status. Manual retry bypasses suspension; policy/source changes change candidate identity. Keep transient recovery. Workspace cancellation acts before transfer and at safe boundaries; never kill an importer during publication. Asset diagnostics retain network denial and exact validation.

## Reconciled deviations

Use the existing admin dispatcher/Reindex endpoints with one compact encoding-policy route, rather than all illustrative new endpoints. Keep retry coordination as a private atomic status alongside existing SQLite jobs; no new queue or schema migration. Preserve accepted fail-closed query readiness after failed refresh, retaining the durable last-good generation. General-purpose exclusion editing is deferred: defaults repair the observed duplicate worktrees in both scanners, while existing Go transfer exclusions remain explicitly separate. See verification.md for external work-PC gates.

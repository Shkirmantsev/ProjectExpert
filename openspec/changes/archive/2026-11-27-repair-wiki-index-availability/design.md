# Design

Use the existing confined LlmWiki reader in the browser. Search the authored files directly, checking the workspace generation across the read. Indexed retrieval and graph expansion continue to require a consistent published snapshot.

Display indexed sources and curated pages separately from embedding progress. Drive Search through local retrieval and expose optional chat as a separate explicit action. Keep automatic export results in the reindex job projection. Check an expiring approval before staging and report its expiry. Use the same relative record identity in both indexing engines, independently of the sharing preference. Project private inbox citations with native paths at search time. Existing absolute-path outputs are rebuilt once on upgrade. The version monitor detects canonical changes from manual publication. A byte-identical publication needs no refresh request.

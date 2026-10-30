# Verification — 2026-10-30

Initial regression tests reproduced absent chat CLI, missing pre-start binding,
missing LOCAL_ONLY on target tmp inputs and exclusion of large tmp PDFs. The
pre-run/UI round-trip test also reproduced credential settings not being Git
ignored before first hydration. These regressions pass after the repair.

| Scenario | Test evidence |
| --- | --- |
| CLI configure before serving, persistent/redacted key, saved consent reuse, disable | `PreRunChatTests.test_cli_configures_before_serve_redacts_key_and_preserves_saved_consent` |
| Pre-run URL/model appear in UI API and UI edits appear in CLI status | `test_prerun_config_is_visible_and_editable_in_ui` |
| Make config precedes up, no dependencies, secret not printed, omitted flag preserves, LLM=0 disables, failure prevents up | `test_make_binding_is_prerun_ordered_and_never_prints_keys` |
| Nested 6 MiB tmp PDF is eligible/private; scratch and cache excluded; content/removal changes monitored | `TmpInputTests.test_tmp_nested_documents_are_private_large_and_monitorable` |
| Small configured limit cannot be bypassed; Git-tracked tmp source remains versioned | `test_tmp_limit_is_not_bypassed_and_tracked_documents_remain_repository_input` |
| Search returns tmp evidence with LOCAL_ONLY and Git check-ignore passes | `test_tmp_documents_search_and_git_exclusion` |

Executed:

- 73 focused CLI/tmp/inbox/ingestion tests PASS (1 optional real-model skip).
- 15 final pre-run/UI-chat tests PASS.
- 14 Make-help/pre-run tests PASS; Make dry-run confirms order and named
  environment forwarding. Tests execute Make with a controlled Compose fixture,
  plus the real CLI and real HTTP UI adapter against a disposable target.
- Node browser-script flow, Python compile checks and git diff check PASS.
- Full `python3 harness.py check` PASS, including strict OpenSpec, Wiki,
  production inventory, isolated repository test modules, project-context tests
  and artifact manifest. Late scanner/credential hardening also passed focused
  regressions; final HTML-only help changes passed the browser-script check.

No trade-analyzer files or live chat credentials were modified. No image was
published or deployed. A real-model repeat was NOT RUN: the previously available
production image and embedding sidecar had been removed from this host; the
`--pull=never` isolated attempt could not find the image. The earlier archived
PDF/Docling/Gemma acceptance remains historical evidence, not a new hardware/model
claim. This change verifies PDF discovery/eligibility and the unchanged parser
routing, and actual text ingestion/search with controlled embeddings.

The intended source inputs are target tmp documents and configured inboxes;
generated tmp/local state, cache/build/vendor directories and symlink escapes
remain excluded. Existing tracked files are not untracked. Raw document indexing
still does not automatically write curated Wiki articles.

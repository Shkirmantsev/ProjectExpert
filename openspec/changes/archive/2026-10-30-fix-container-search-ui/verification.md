# Verification evidence — 2026-10-30

## Regression cycle

The initial focused tests reproduced: omitted inbox files (including a 6 MiB
PDF), no published repository sources, readiness errors losing their cause,
refused Open WebUI streaming and retrieval falsely used as delegation. After
the repairs, the same paths pass. The real PDF integration then exposed lost
LOCAL_ONLY metadata in the PDF document projection. A unit regression for first
and cached parses failed before the metadata fix and passes afterwards.

| Scenario | Evidence |
| --- | --- |
| Inbox search, edit/delete, source catalog and policy | `tests.test_container_search_ui.ContainerSearchTests` |
| Custom inbox and Git exclusion | `test_indexing_excludes_inbox_from_git_and_supports_configured_path` |
| PDF size and symlink exclusion | `test_inbox_pdf_uses_its_larger_limit_and_skips_symlink_trees` |
| HTTP 503 diagnostics | `test_unready_http_preserves_actual_failure` |
| HTTP OpenAI SSE without chat LLM | `test_sse_search_is_usable_without_chat_model` |
| Delegation cannot falsely succeed | `test_delegation_cannot_report_success_for_retrieval_only` |
| Browser job progress, terminal errors, auth separation and readable Wiki | `node tests/ui_container_search.test.js` PASS |
| PDF policy survives fresh/cached parsing | `tests.test_docling_pdf_adapter.DoclingPdfAdapterSmokeTests.test_pdf_projection_preserves_local_policy_on_first_and_cached_parse` |
| Actual PDF → Docling → Gemma → USearch retrieval | `tests.test_container_search_ui.RealInboxModelTests` PASS in isolated production-dependency container; `PI_RUN_INBOX_MODEL_TESTS=1` |

The real PDF run used the patched checkout read-only, disposable target files,
task-only temporary Docling/HF caches, the existing managed Gemma sidecar and
read-only mounts of the deployed model cache. It verified nonempty retrieval,
PDF source provenance, LOCAL_ONLY on every hit, unchanged PDF bytes and no
implicitly generated canonical Wiki. First-use assets were downloaded; an earlier
attempt with a read-only empty Docling cache was an unsuitable test environment,
not evidence that deployed PDF conversion works without provisioned assets.

## Executed checks

- 148 focused existing/new tests: PASS, 3 optional skips at that run.
- 47 final inbox/discovery/PDF tests: PASS, 1 opt-in real-model skip on the host;
  the real-model case ran separately in the production container and passed.
- 36 production-dependency tests (including native ANN/recovery): PASS in a
  disposable container. The controlled-embedding tests do not measure model
  quality; only the explicit PDF integration uses real Gemma inference.
- Node UI flow and JavaScript syntax: PASS.
- `docker compose --profile open-webui config --services`: only `core` and
  `open-webui`; no placeholder chat sidecar.
- `git diff --check`: PASS.
- `python3 harness.py check`: PASS (configuration, session state, Wiki, strict OpenSpec validation, capability inventory, isolated repository test modules, project-context tests and artifact manifest).
- The first restricted-sandbox full-gate attempt could not bind test HTTP sockets; the full gate was rerun with loopback access and passed.

## Deployment limits

No new image was published or deployed, and no Open WebUI account settings or
trade-analyzer files were edited. Live read-only checks found 345 sources and
3,470 chunks; Ask and retrieve currently returned HTTP 200. Prior logs showed
refresh retries after concurrent source changes and an invalid Python f-string
in `backtest_v4_modified.py:29`.

The UI does not implement upstream chat LLM calls or automatic LLM Wiki synthesis.
Materialisation and external delegation remain controlled operations, not search
prerequisites. SSE is finite transport framing of retrieved evidence. GPU and
Windows execution were not re-certified by this UI/inbox change.

The accepted historical requirement says the optional Open WebUI flag defaults
off, while the existing implementation/tests default it on. This pre-existing
mismatch was observed and is not silently changed by the SSE/UI repair.

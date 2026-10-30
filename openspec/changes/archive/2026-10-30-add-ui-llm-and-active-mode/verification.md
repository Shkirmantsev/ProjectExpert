# Verification — 2026-10-30

The initial six new regression tests failed before the adapter/status implementation.
The final suite exercises actual loopback HTTP provider fixtures (OpenAI-compatible
and Anthropic request/response contracts), not real paid-provider accounts.

| Scenario | Regression evidence |
| --- | --- |
| Atomic persistent settings, mode 0600, redacted GET, key retention/removal | `ChatConnectionTests.test_save_is_persistent_redacted_and_owner_only` |
| OpenAI and Anthropic payloads and safe 401 diagnostic | `test_provider_payload_and_diagnostic_do_not_expose_keys` |
| Grounded generated answer, evidence fallback, deterministic retrieval independence, disabled mode and generation change | `test_optional_grounded_query_and_fallback_keep_retrieval_independent` |
| Admin HTTP settings/test, denied agent writes, Open WebUI SSE generated answer, provider failure and recursion rejection | `test_admin_http_configuration_test_and_openwebui_share_connection` |
| Consent/URL validation | `test_requires_context_consent_and_valid_url` |
| Egress denial sends nothing | `test_context_egress_denial_does_not_send_or_drop_evidence` |
| Remote INTERNAL sharing has scoped approval; external CONFIDENTIAL blocked | `test_remote_context_needs_scoped_operator_approval_and_classification` |
| Actual mode distinct from Auto; managed CPU/Hybrid and legacy kit; unknown remote | `EffectiveModeTests` |
| Browser save/apply/test, hidden keys, generated answer and CPU/Hybrid badge | `node tests/ui_container_search.test.js` |

Executed checks:

- New chat/effective-mode suite: 9 tests PASS.
- Existing/new focused UI/retrieval/embedding compatibility suite: 131 tests PASS,
  2 optional skips at that run. Final targeted suites after late hardening: 39
  tests PASS (1 optional model skip), 16 PASS and 46 PASS.
- Node browser-script flow and syntax: PASS.
- Compose CPU/CUDA/Vulkan configuration matrix: effective backend and Linux host
  gateway mapping PASS. Open WebUI profile still starts no dummy chat model.
- `python3 harness.py check`: PASS including configuration, session state, Wiki,
  strict OpenSpec, capability inventory, isolated repository test modules,
  project-context tests and artifact manifest. Final source hardening was also
  checked by the targeted tests above.
- Final `git diff --check`, Wiki, strict OpenSpec and artifact checks: PASS.

Limits: no real Anthropic credentials or user LM Studio instance was configured;
no new image was built/published/deployed and no trade-analyzer settings changed.
No new physical GPU/Windows acceptance is claimed. Native mode reports the loaded
adapter device. Managed Hybrid is a selected GPU backend with forced CPU projector,
not a measured per-layer offload statistic. Unknown remote hardware remains Unknown.
The existing accepted-default-off versus implementation-default-on Open WebUI flag
mismatch is unchanged and remains documented in the preceding repair evidence.

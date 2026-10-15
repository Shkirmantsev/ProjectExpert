---
id: interfaces.local-contextualizer
title: LocalContextualizer contract
kind: interfaces
status: active
summary: Narrow application service over LocalLLMPort for indexing-time enrichment. Forbidden from producing authoritative metadata; LRU-cached by content hash + model revision + prompt version + enrichment strategy version.
sourceRefs:
  - pi_platform/core/ingest/local_contextualizer.py
  - pi_platform/ports/ingest/inference_policy.py
  - pi_platform/ports/orchestration/local_llm.py
  - openspec/changes/improve-ingestion-retrieval-local-models/specs/2026-10-04-context-enrichment/spec.md
  - adr.0027-inference-policy-separate-from-source-policy
maintenance:
  mode: authored
related:
  - interfaces.inference-policy
  - interfaces.retrieval-text-builder
  - modules.enrichment
  - modules.llm-port
---

# LocalContextualizer contract

The v0.8 refinement introduces a `LocalContextualizer`
application service over the existing `LocalLLMPort`. Its
job is limited to indexing-time enrichment: a 1–3 sentence
semantic context, candidate entities, candidate relations,
query aliases / glossary hints. It is forbidden from
producing authoritative metadata.

The implementation lives at
`pi_platform/core/ingest/local_contextualizer.py`.

## Allowed outputs

- `summary` — 1–3 sentence semantic context (truncated to
  `max_summary_chars`, default 480).
- `candidate_entities` — tuple of strings.
- `candidate_relations` — tuple of strings.
- `query_aliases` — tuple of strings.

## Forbidden authoritative outputs

The response parser drops the following keys before
returning the summary, even if the LLM produced them:

- `requirement_id`
- `protocol_version`
- `validFrom`
- `validTo`
- `security_class`
- `git_revision`
- `source_id`
- `license`

These come only from deterministic / trusted sources. The
contract test
`test_authoritative_metadata_not_overwritten` asserts that
the canonical `Chunk.metadata.requirementId` is unchanged
even when the contextualizer returns a non-empty
`requirement_id` in the response.

## InferencePolicy gating

When `InferencePolicy = NO_MODEL`, the contextualizer
returns an empty `LocalContextSummary` without invoking
the LLM. The contract test
`test_inference_policy_no_model_blocks_llm_call` asserts
the stub LLM is not called.

When `InferencePolicy = LOCAL_MODEL_ALLOWED`, the
contextualizer calls the LLM. The prompt is a fixed
template that includes only `document title`, `heading
path`, `neighbour text`, and `chunk rawText` — never
authoritative fields.

## Cache key

`sha256(chunk_content_hash || model_revision || family ||
prompt_version || enrichment_strategy_version ||
neighbour_text)`.

A Git branch switch reuses the cached result when content
and strategy are unchanged. A model upgrade, a prompt
change, or an enrichment strategy change invalidates the
cache. The contract test
`test_cache_key_changes_with_enrichment_strategy_version`
asserts the strategy-version dimension.

## Allowed `model_kind` values

- `"local"` — `LOCAL_MODEL_ALLOWED` permits; `NO_MODEL`
  forbids; `EXTERNAL_MODEL_ALLOWED` permits.
- `"external"` — only `EXTERNAL_MODEL_ALLOWED` permits.

An unknown `model_kind` raises `ValueError` from
`policy_allows`.

## v0.8 invariants preserved

- The existing `LocalLLMPort` is unchanged; the
  `LocalContextualizer` is a thin application service on
  top.
- Authoritative metadata is never overwritten by the local
  LLM.
- The legacy `context.extra["local_llm"]` binding path is
  still available when neither `inference_policy` nor
  `local_contextualizer` is set.

## Tests

- `tests/test_local_contextualizer.py` (15 tests) — policy
  gating, fixed prompt, parsing, forbidden-key filter,
  truncation, cache key (model revision, prompt version,
  enrichment strategy version), cache hit, authoritative
  metadata not overwritten, enricher byte-identical
  without contextualizer.
- `tests/test_inference_policy.py` (7 tests) — `NO_MODEL`
  blocks, `LOCAL_MODEL_ALLOWED` and `EXTERNAL_MODEL_ALLOWED`
  call LLM, `policy_allows` policy validation.

[Inference policy](inference-policy.md) ·
[Retrieval text builder](retrieval-text-builder.md) ·
[Local LLM port](../modules/llm-port.md) ·
[ADR 0027](../adr/0027-inference-policy-separate-from-source-policy.md)

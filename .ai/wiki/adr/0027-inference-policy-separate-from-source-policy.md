---
id: adr.0027-inference-policy-separate-from-source-policy
title: InferencePolicy separate from SourcePersistencePolicy
kind: adr
status: accepted
date: 2026-10-14
summary: The model-exposure policy (NO_MODEL / LOCAL_MODEL_ALLOWED / EXTERNAL_MODEL_ALLOWED) is decoupled from the source-persistence policy (LOCAL_ONLY / REFERENCE / SNAPSHOT). Both are evaluated by the central Policy Engine, but they answer orthogonal questions and the local LLM is no longer gated by source persistence alone.
related:
  - adr.0004-ports-and-adapters-extension-style
  - adr.0017-phase-8-enterprise-security-boundary
  - adr.0025-rerank-direct-before-graph-expansion
  - interfaces.policy-engine
  - interfaces.secret-provider
  - modules.security
  - modules.llm-port
  - modules.enrichment
sourceRefs:
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#3.4
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#11.1
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#11.2
  - openspec/changes/archive/2026-10-16-improve-ingestion-retrieval-local-models/specs/2026-10-04-context-enrichment/spec.md
  - pi_platform/ports/ingest/inference_policy.py
  - pi_platform/core/ingest/local_contextualizer.py
  - pi_platform/ports/ingest/context_enricher.py
  - pi_platform/adapters/ingest/layered_context_enricher.py
maintenance:
  mode: authored
---

# ADR 0027 — InferencePolicy separate from SourcePersistencePolicy

## Context

The v0.8 `LayeredContextEnricher` conflated two orthogonal
policies when invoking the optional local LLM:

- **Source persistence policy** (`Metadata.policy` ∈
  `{LOCAL_ONLY, REFERENCE, SNAPSHOT}`) — describes how the
  source is stored on disk. A `LOCAL_ONLY` source never
  leaves the operator's machine; a `SNAPSHOT` source may be
  mirrored to Git or LFS.
- **Model exposure policy** — describes whether the source
  content may be processed by a model at all, and which
  kind. The plan calls this out as a separate axis (plan
  §11.1): the two policies answer different questions.

The v0.8 code only invoked the local LLM when the source
persistence policy was `LOCAL_ONLY` or `REFERENCE` and
`context.extra["allow_local_llm"]` was true. This had two
unwanted consequences:

1. A `SNAPSHOT` source was never LLM-enriched even when the
   operator explicitly wanted it to be (e.g. an offline
   ingestion of a snapshot corpus that the operator is
   happy to feed to a local model).
2. The Policy Engine had no clean way to audit "did this
   chunk get sent to a model" separately from "where is
   this chunk stored".

In addition, the v0.8 enricher stored the LLM suggestion
under `meta.extensions["pi_assumption"]["contextPrefix"]`
and never actually used it to build the text that was
embedded; the embedding input was the deterministic prefix
only. So even when the policy allowed the LLM, the result
was wasted.

## Decision

Introduce a separate `InferencePolicy` enum with three
values:

- `NO_MODEL` — no model is permitted to see the content;
  this is the default. The `LocalContextualizer` returns an
  empty `LocalContextSummary` without invoking the LLM.
- `LOCAL_MODEL_ALLOWED` — a local model (LLM, embedding
  model, or reranker running on the operator's machine) is
  permitted. The `LocalContextualizer` calls the local LLM
  through the existing `LocalLLMPort`.
- `EXTERNAL_MODEL_ALLOWED` — an external (network) model is
  permitted; the central Policy Engine still authorises
  individual calls. The local LLM is also permitted.

`SourcePersistencePolicy` (`LOCAL_ONLY | REFERENCE |
SNAPSHOT`) is unchanged. The two policies are evaluated
independently. A source with `SourcePersistencePolicy =
LOCAL_ONLY` may still be processed by a local model if
`InferencePolicy = LOCAL_MODEL_ALLOWED`; the central Policy
Engine authorises the call and records the decision in the
audit log.

The `LocalContextualizer` is a narrow application service
over the existing `LocalLLMPort`. Its job is limited to
indexing-time enrichment: a 1–3 sentence semantic context,
candidate entities, candidate relations, query aliases /
glossary hints. It is forbidden from producing authoritative
metadata: `requirement_id`, `protocol_version`, `validFrom`,
`validTo`, `security_class`, `git_revision`, `source_id`,
`license`. The LLM response is parsed as `key: value`
lines; any forbidden authoritative key is dropped before
the result is returned. The remaining summary is truncated
to `max_summary_chars` (default 480).

The contextualization cache key is
`sha256(chunk_content_hash || model_revision || prompt_version
|| enrichment_strategy_version)`. A Git branch switch
reuses the cached result when content and strategy are
unchanged; a model upgrade or a prompt change invalidates
the cache.

`RetrievalTextBuilder` (Change Package B4) builds the
final `retrieval_text` as
`deterministic context prefix + "\n\n" + raw_text`, with
the model-generated context appended under `inferred: `
only when the `LocalContextualizerRetrievalTextBuilder`
is wired. The default `DeterministicRetrievalTextBuilder`
ignores the local enrichment, so the deterministic profile
is byte-identical with and without the local LLM.

The `EnricherContext` gained two additive optional fields:
`inference_policy: InferencePolicy = NO_MODEL` and
`local_contextualizer: LocalContextualizer | None = None`.
When both are set and `context.enable_optional_llm` is
true, the enricher calls the contextualizer; otherwise the
legacy `context.extra["local_llm"]` binding path runs
byte-identically.

## Consequences

Positive:

- The model-exposure decision is auditable separately from
  the storage decision; operators can grant one without
  the other.
- The local LLM's output is now actually used: the
  `LocalContextualizerRetrievalTextBuilder` appends the
  semantic context to the embedding input under `inferred: `.
- Forbidden authoritative fields cannot leak into the
  embedding input even if the LLM produces them; the
  response parser drops them deterministically.
- Branch-switch hydration reuses cached contextualization
  when content and strategy are unchanged; the cache key
  is content-hash-based and busts on model or prompt
  upgrades.

Negative:

- The Policy Engine integration is not yet complete: the
  `LocalContextualizer` does not yet call
  `DefaultPolicyEngine.evaluate(...)` for the
  `InferencePolicy` decision. This is recorded as a
  follow-up in the `context-impact.md` and is left for
  Package I (Control Plane / MCP polish). The current
  behaviour is that the `InferencePolicy` is checked
  inside the contextualizer, which is sufficient for
  the contract; the audit log is not yet populated.
- The `LocalContextualizer` requires a `LocalLLMPort`
  binding even when `NO_MODEL` is selected. The
  constructor is permissive; the policy check returns
  immediately without calling `complete()`.

## Rollback

Set the default `InferencePolicy` back to the legacy
behaviour by changing `DEFAULT_INFERENCE_POLICY` in
`pi_platform/ports/ingest/inference_policy.py` and the
`inference_policy` field default in `EnricherContext` to
match the v0.8 coupling logic. The legacy
`context.extra["local_llm"]` binding path is still
available; the new path is purely additive.

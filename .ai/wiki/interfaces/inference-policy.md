---
id: interfaces.inference-policy
title: InferencePolicy contract
kind: interfaces
status: active
summary: Decouples the model-exposure policy (NO_MODEL / LOCAL_MODEL_ALLOWED / EXTERNAL_MODEL_ALLOWED) from the source-persistence policy (LOCAL_ONLY / REFERENCE / SNAPSHOT). The two are evaluated independently by the central Policy Engine.
sourceRefs:
  - pi_platform/ports/ingest/inference_policy.py
  - pi_platform/core/ingest/local_contextualizer.py
  - pi_platform/ports/ingest/context_enricher.py
  - pi_platform/adapters/ingest/layered_context_enricher.py
  - openspec/changes/improve-ingestion-retrieval-local-models/specs/2026-10-04-context-enrichment/spec.md
  - adr.0027-inference-policy-separate-from-source-policy
maintenance:
  mode: authored
related:
  - interfaces.local-contextualizer
  - interfaces.retrieval-text-builder
  - modules.enrichment
  - adr.0017-phase-8-enterprise-security-boundary
---

# InferencePolicy contract

The v0.8 refinement introduces a separate `InferencePolicy`
enum to answer the question "may this content be processed
by a model?" The question is orthogonal to "how is this
content stored?" — the answer is `SourcePersistencePolicy`.

The port lives at
`pi_platform/ports/ingest/inference_policy.py`.

## Enum

```python
class InferencePolicy(str, enum.Enum):
    NO_MODEL = "NO_MODEL"
    LOCAL_MODEL_ALLOWED = "LOCAL_MODEL_ALLOWED"
    EXTERNAL_MODEL_ALLOWED = "EXTERNAL_MODEL_ALLOWED"
```

`DEFAULT_INFERENCE_POLICY = NO_MODEL`.

## policy_allows

```python
def policy_allows(policy: InferencePolicy, *, model_kind: str) -> bool:
    """Return True iff `model_kind in {"local", "external"}` is permitted."""
```

`EXTERNAL_MODEL_ALLOWED` permits both `local` and `external`
model kinds. `LOCAL_MODEL_ALLOWED` permits only `local`.
`NO_MODEL` permits neither. An unknown `model_kind` raises
`ValueError`.

## Decoupling

| Question | Answer enum | Default |
| --- | --- | --- |
| How is the source stored? | `SourcePersistencePolicy` (`LOCAL_ONLY` / `REFERENCE` / `SNAPSHOT`) | per source |
| May a model see the content? | `InferencePolicy` (`NO_MODEL` / `LOCAL_MODEL_ALLOWED` / `EXTERNAL_MODEL_ALLOWED`) | `NO_MODEL` |

The v0.8 code conflated the two by gating the local LLM
on `SourcePersistencePolicy in {LOCAL_ONLY, REFERENCE}`.
The v0.8 refinement decouples them: a `SNAPSHOT` source may
be processed by a local model if `InferencePolicy =
LOCAL_MODEL_ALLOWED`; the central Policy Engine authorises
the call and records the decision in the audit log.

## v0.8 invariants preserved

- `SourcePersistencePolicy` is unchanged.
- The legacy `context.extra["local_llm"]` binding path is
  still available when neither `inference_policy` nor
  `local_contextualizer` is set; the new path is purely
  additive.
- The default `NO_MODEL` policy is safe-by-default: a
  chunk is only sent to a model when the operator
  explicitly enables it.

## Tests

- `tests/test_inference_policy.py` (7 tests) — NO_MODEL
  blocks LLM call, LOCAL_MODEL_ALLOWED calls LLM,
  EXTERNAL_MODEL_ALLOWED calls LLM, forbidden authoritative
  fields filtered, cache key changes with model revision,
  cache key changes with prompt version, cache hit doesn't
  call LLM, authoritative metadata not overwritten.

[Local contextualizer](local-contextualizer.md) ·
[Retrieval text builder](retrieval-text-builder.md) ·
[ADR 0027](../adr/0027-inference-policy-separate-from-source-policy.md)

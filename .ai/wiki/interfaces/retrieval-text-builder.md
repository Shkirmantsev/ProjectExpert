---
id: interfaces.retrieval-text-builder
title: RetrievalTextBuilderPort contract
kind: interfaces
status: active
summary: Distinguishes raw_text (exact source text) from retrieval_text (text actually passed to the embedding model) and from metadata. The local LLM is forbidden from producing authoritative metadata and its summary lands in the retrieval_text only when the LocalContextualizerRetrievalTextBuilder is wired.
sourceRefs:
  - pi_platform/ports/ingest/retrieval_text_builder.py
  - pi_platform/core/ingest/retrieval_text_builder.py
  - openspec/changes/archive/2026-10-16-improve-ingestion-retrieval-local-models/specs/2026-10-04-context-enrichment/spec.md
  - openspec/changes/archive/2026-10-16-improve-ingestion-retrieval-local-models/specs/2026-10-04-semantic-structural-chunking/spec.md
  - adr.0027-inference-policy-separate-from-source-policy
maintenance:
  mode: authored
related:
  - interfaces.tokenizer
  - interfaces.inference-policy
  - interfaces.local-contextualizer
  - modules.enrichment
---

# RetrievalTextBuilderPort contract

The v0.8 refinement introduces a `RetrievalTextBuilderPort` so
the embedding model never receives raw metadata JSON. The
builder produces a `RetrievalText` value object that carries
both the deterministic context prefix and (optionally) the
local-LLM-generated context, with forbidden fields explicitly
excluded.

The port lives at
`pi_platform/ports/ingest/retrieval_text_builder.py`. The
implementations live at
`pi_platform/core/ingest/retrieval_text_builder.py`.

## Surface

```python
@dataclass(frozen=True)
class RetrievalText:
    text: str
    strategy_version: str
    deterministic_parts: tuple[str, ...]
    inferred_parts: tuple[str, ...]
    content_hash: str   # sha256 hex of the text


class RetrievalTextBuilderPort(abc.ABC):
    @abstractmethod
    def build(
        self, *, chunk, document, section, metadata,
        local_enrichment=None,
    ) -> RetrievalText: ...
```

`DEFAULT_STRATEGY_VERSION = "retrieval-text-v1"`.

## Implementations

| Builder | Behaviour |
| --- | --- |
| `DeterministicRetrievalTextBuilder` (default) | Joins a fixed semantic allowlist as `key: value` lines, then `"\n\n"` + `raw_text`. Ignores `local_enrichment`. The `minimal` profile uses this builder. |
| `LocalContextualizerRetrievalTextBuilder` (opt-in) | When `local_enrichment.context_summary` is provided, appends it under `inferred: ` and records it in `inferred_parts`. Otherwise delegates to the default builder. Forbidden authoritative keys are dropped from the inferred text. |

## Allowed semantic fields (deterministic)

- `document.title`
- `metadata.section`
- `metadata.businessDomain`
- `metadata.module`
- `metadata.className`
- `metadata.requirementId` (when semantically meaningful)
- `metadata.extensions["caption"]`
- `metadata.extensions["protocol_name"]`

The `local_enrichment.context_summary` (when present) lands
under `inferred: <summary>` in the inferred part.

## Forbidden fields (NEVER embedded)

The builder enforces a hard exclusion list at build time;
encountering any of these raises `RetrievalTextBuilderError`:

- absolute filesystem path
- SHA digest
- Git commit hash
- timestamp
- bbox coordinates
- security label
- processing version

These remain metadata.

## v0.8 invariants preserved

- `Chunk.raw_text` (the exact source text) is unchanged.
- `Chunk.metadata` (the exact filters, provenance, version /
  security fields) is unchanged.
- The legacy `Chunk.contextualText` mapping is reconciled
  to a single canonical meaning: it mirrors
  `RetrievalText.text` when the pipeline driver writes
  `extensions["retrieval_text"]` and
  `extensions["retrieval_text_hash"]`.
- Authoritative metadata is never overwritten by the local
  LLM: the response parser drops forbidden authoritative
  keys before the summary reaches the builder (see
  `interfaces.local-contextualizer`).

## Tests

- `tests/test_retrieval_text_builder.py` (11 tests) —
  excludes forbidden fields, includes semantic fields,
  content_hash stable, local summary appended (subclass only),
  default ignores local_enrichment, single canonical mapping
  for retrieval_text.
- `tests/test_v2_production_wiring.py` — pipeline driver
  references the builder.

[Context enrichment](enrichment.md) ·
[Inference policy](inference-policy.md) ·
[Local contextualizer](local-contextualizer.md) ·
[ADR 0027](../adr/0027-inference-policy-separate-from-source-policy.md)

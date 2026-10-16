---
id: interfaces.tokenizer
title: TokenizerPort contract
kind: interfaces
status: active
summary: Tokenizer port for embedding-tokenizer-aware chunk sizing. Additive layer above the existing structural chunkers; default is the stdlib-only HashingTokenizer.
sourceRefs:
  - pi_platform/ports/ingest/tokenizer.py
  - pi_platform/adapters/ingest/tokenizers.py
  - pi_platform/core/ingest/token_budget.py
  - openspec/changes/archive/2026-10-16-improve-ingestion-retrieval-local-models/specs/2026-10-04-semantic-structural-chunking/spec.md
  - openspec/specs/2026-10-16-embedding-execution-profile/spec.md
maintenance:
  mode: authored
related:
  - interfaces.chunker
  - interfaces.embedding-profile
  - modules.ingest
---

# TokenizerPort contract

The v0.8 refinement adds a `TokenizerPort` so the
`TokenBudgetNormalizer` (composition: structural boundary →
tokenizer-aware split → merge compatible peers) can size chunks
to the actual embedding tokenizer, not to UTF-8 bytes.

The port lives at `pi_platform/ports/ingest/tokenizer.py`. The
adapters live at `pi_platform/adapters/ingest/tokenizers.py`.

## Surface

```python
class TokenizerPort(abc.ABC):
    @abstractmethod
    def count(self, text: str) -> int: ...

    @abstractmethod
    def truncate(self, text: str, max_tokens: int) -> str: ...

    @abstractmethod
    def identity(self) -> str: ...
```

`identity()` returns a stable, hierarchical token such as
`hashing/v1`, `whitespace/v1`, or `embeddinggemma2/v1-stub`.

## Adapters

| Adapter | Identity | Notes |
| --- | --- | --- |
| `WhitespaceTokenizer` | `whitespace/v1` | Splits on whitespace; test fallback. |
| `HashingTokenizer` | `hashing/v1` | Stdlib-only; deterministic byte-stable count via sha256-per-char weights; LRU-cached. The default in the `minimal` profile. |
| `EmbeddingGemma2Tokenizer` | `embeddinggemma2/v1-stub` | **Stub**: `count()` and `truncate()` raise `TokenizerError("not bound in minimal profile; install semantic-embeddings extras in C")`. The real binding ships in Package C.1.5. |

## ChunkerContext extension (additive)

`pi_platform/ports/ingest/chunker.py::ChunkerContext` gained
additive optional fields:

- `target_tokens: Optional[int] = None`
- `max_tokens: Optional[int] = None`
- `min_tokens: Optional[int] = None`
- `tokenizer_id: str = ""`
- `merge_peers: bool = True`

The existing `max_chunk_bytes` field is preserved as a hard
safety limit. When none of the new token fields are set, the
legacy byte-based path runs byte-identically.

## TokenBudgetNormalizer

`pi_platform/core/ingest/token_budget.py` exposes
`TokenBudgetNormalizer` and `wrap(structural_chunker) ->
ChunkerPort`. The wrapper calls the structural chunker and
post-processes each result chunk's `rawText` through the
normalizer while preserving `id`, `parentId`, and `metadata`.

Algorithm:

1. Split oversized candidates at token boundaries (preserving
   word/paragraph/sentence when possible).
2. Merge compatible peer candidates when below `min_tokens`
   AND `merge_peers=True` AND the merged result fits
   `max_tokens`.
3. Never violate `max_chunk_bytes` (UTF-8 byte hard limit).
4. Raise `TokenizerError` if a single word exceeds
   `max_tokens` (a chunker-level error; structural chunkers
   upstream must produce smaller candidates).

The wrapper is wired into
`pi_platform/adapters/ingest/local_pipeline_driver.py` via
lazy import; production code activates it when
`ChunkerContext.target_tokens` or `max_tokens` is set.

## v0.8 invariants preserved

- All existing structural chunkers
  (`PlainTextChunker`, `MarkdownChunker`, `HtmlChunker`,
  `RequirementIdChunker`, `ProtocolMessageChunker`,
  `TableChunker`, `ArchitectureUnitChunker`) remain.
- `ChunkerContext` extension is additive; legacy
  `ChunkerContext(max_chunk_bytes=4096)` constructs with all
  new fields defaulted.
- Same input + same strategy + same tokenizer produce
  deterministic chunks.
- `tests/test_platform_phase2.py` (41 tests) continues to
  pass byte-identically.

## Tests

- `tests/test_tokenizer_port.py` (18 tests) — count, truncate,
  determinism, stub raises, identity non-empty.
- `tests/test_chunker_context_additive.py` (7 tests) —
  defaults byte-identical, negative rejected, fields accepted.
- `tests/test_token_budget.py` (18 tests) — split, merge,
  no-merge-when-disabled, max_chunk_bytes never violated,
  oversized word raises, wrap preserves metadata, wrap
  byte-identical when no token context, chunking determinism.
- `tests/test_v2_production_wiring.py` — pipeline driver
  wiring smoke test.

[Chunker interface](chunker.md) ·
[Embedding profile](embedding-profile.md) ·
[Ingestion pipeline](../modules/ingest.md)

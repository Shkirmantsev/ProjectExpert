# 2026-10-04-reranker-port Specification delta

Covers plan §18, §18.1, §18.2.

## ADDED Requirements

### Requirement: reranker profile set

The platform MUST support the following reranker
profiles as configuration presets, not code paths:

- `minimal` — BM25-light fallback (zero dependencies);
- `fast` — optional compact cross-encoder (e.g. a
  validated multilingual SentenceTransformers
  `CrossEncoder`);
- `quality` — `Qwen3-Reranker-0.6B` on CPU (opt-in
  because the model artifact is ~1.2 GB);
- `experimental` — ColBERT-style adapter.

The existing `CrossEncoderRerankerAdapter` is a
constructor-only placeholder; this delta requires it
to be a real adapter against a SentenceTransformers
`CrossEncoder`.

#### Scenario: minimal profile is dependency-light

Given the `minimal` profile and no optional
dependencies installed
When the platform runs a retrieval
Then the reranker is the BM25-light fallback
And no GPU or heavyweight model is loaded.

### Requirement: bounded rerank_text

The reranker MUST consume a bounded `rerank_text`
built from `document_title`, `heading_path`,
`raw_chunk`, `caption`, and `class/method context`.
The rerank_text MUST NOT contain hashes, bbox,
timestamps, Git SHA, or unrelated metadata. The
budget is `max_pair_tokens` (default 1536 — a
starting experiment, not a permanent contract).
Inferred enrichment is trimmed before raw evidence.

#### Scenario: rerank_text excludes forbidden fields

Given a chunk whose metadata contains a SHA, a Git
commit hash, a timestamp, a bbox, and an unrelated
`api_key`
When the platform builds `rerank_text`
Then none of those fields appear
And the chunk is still ranked by the cross-encoder.

### Requirement: timeouts, batching, and CPU fallback

The reranker MUST enforce bounded timeouts, batch
sizes, and concurrency. On timeout or error the
reranker MUST fall back to the RRF ordering of the
pre-rerank direct candidate pool. The fallback MUST
be recorded in the `RetrievalTrace.reranker` section.

#### Scenario: reranker timeout falls back to RRF

Given a reranker profile with `timeout_seconds: 8`
When the cross-encoder call exceeds the timeout
Then the platform returns the RRF-ordered direct
candidate pool as the rerank output
And the `RetrievalTrace.reranker` records the
fallback.

## MODIFIED Requirements

None. The existing reranker-port `Requirements` are
extended additively; their bodies are not rewritten.

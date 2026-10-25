# Fix the rerank decision propagation

## Why

The reranker sorted the candidates by its own score but returned them with
the OLD retrieval score. The selection stage then re-sorted by that old
score, so the rerank was silently undone: a candidate the reranker had
promoted could still end up below a candidate it had demoted.

Two further gaps made the effect invisible in practice:

* reranking was opt-in per query and the MCP search / retrieve-context
  tools never asked for it, so the reranker usually did not run at all;
* a failing reranker degraded gracefully only in the twelve-stage path;
  the legacy path propagated the failure.

A text-only reranker also demoted media candidates: a visually relevant
image whose textual representation does not contain the query terms was
pushed to the bottom even though the multimodal embedding space had ranked
it highly.

## What changes

* A reranked hit carries the reranker's own score and rank. The retrieval
  score is preserved unchanged for fallback and diagnostics.
* The selection stage orders candidates by the rerank decision: a reranked
  candidate is ordered by its rerank rank, and a candidate that was never
  reranked keeps the retrieval-score order.
* Reranking becomes operator-controllable: an enabled flag, a family, a
  candidate count, a timeout and a fallback mode. BM25-light reranking is
  active by default and can be switched off explicitly.
* A query may override the policy; the MCP search and retrieve-context
  tools expose that override.
* A failing reranker degrades to the pre-rerank order in BOTH the legacy
  and the twelve-stage path, unless the operator selects the failing
  fallback mode.
* The reranker is modality-aware: a media candidate is not scored by the
  text reranker and keeps its retrieval order.

## Impact

Affects the reranker port and core, the candidate selection core, the
multi-stage retrieval pipeline, the retrieval settings, the runtime
configuration resolver and the MCP retrieval tools.

* **Compatibility:** the additive `rerankScore` / `rerankRank` fields on
  `RetrievalHit` and the additive reranking fields on `RetrievalSettings`
  keep existing callers working. The selection order changes only where a
  reranker actually ran.
* **Migration:** none. Persisted vectors and indexes are unaffected.
* **Not in scope:** a neural reranker. The BM25-light family stays the
  production reranker; it is cheap and it is what the operator asked to
  keep.

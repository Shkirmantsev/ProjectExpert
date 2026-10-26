# Design — rerank decision propagation

## The defect

`Bm25LightRerankerCore.rerank` computed a BM25-light score per candidate,
sorted by that score and returned the candidates **with their original
retrieval score**. `SelectionCore.select` then sorted by
`(-hit.score, hit.chunkId)` — the original retrieval score — so the
rerank was undone. A candidate the reranker demoted could still be
selected above one it promoted.

## The fix

Three additive fields on `RetrievalHit`:

* `rerankScore: float | None` — the reranker's own score;
* `rerankRank: int` — the 1-based position in the reranker's ordering.

The retrieval `score` is untouched. The reranker stamps both fields; a
reranker that does not stamp them still has its ordering recorded by
`ensure_rerank_order`, because the order is the decision.

`SelectionCore` orders by `_effective_order_key`:

1. a reranked candidate (`rerankRank > 0`) by its rank;
2. a candidate with only a rerank score by that score;
3. a candidate that was never reranked by its retrieval score, after the
   reranked group.

The per-candidate trace records the rerank score and rank, so the
decision is diagnosable.

## The policy

`RerankPolicy(enabled, family, top_n, timeout_ms, fallback)` is the
operator-controllable configuration. It is carried by the retrieval
settings, the runtime configuration and the multi-stage service.

`RetrievalQuery.enableReranking` becomes `Optional[bool]`: `None` means
"use the policy", `True`/`False` force the decision for that query. The
MCP retrieval tools expose the override.

BM25-light stays the production family. No neural reranker is added.

## Degradation

Both pipeline paths catch a reranker failure and keep the pre-rerank
order. The legacy path previously propagated the failure; it now behaves
like the twelve-stage path. `fallback="fail"` restores the propagating
behaviour for an operator who wants it.

## Modality awareness

A chunk embedded together with an image, a recording or a clip carries
`extensions["media"]` in its metadata. The text reranker does not score
such a candidate: it cannot see the pixels, so scoring it on its empty
textual representation would demote a candidate the multimodal embedding
space ranked highly. Media candidates keep their retrieval order, and
the media group is placed by the position its best candidate held in the
retrieval order — never below a text candidate merely because of an
empty text representation.

The marker survives a restart because the dense index stores the chunk
metadata with the vector and returns it with the match.

## Alternatives rejected

* **Re-sort by the rerank score inside the selection.** Rejected: the
  reranker's rank is authoritative and mixing the two scales loses the
  ordering when the reranker returns fewer candidates than the pool.
* **A neural reranker now.** Rejected by the operator: the cheap text
  family is what the deployment needs, and its speed is a requirement.
* **Dropping media candidates from the reranked pool.** Rejected: they
  must stay visible to the caller.

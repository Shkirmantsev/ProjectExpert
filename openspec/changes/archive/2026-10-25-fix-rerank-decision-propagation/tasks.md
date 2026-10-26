# Tasks — rerank decision propagation

- [x] Add the additive `rerankScore` / `rerankRank` fields to `RetrievalHit`
      and preserve them where hits are rebuilt.
- [x] Stamp the reranker's score and rank in the BM25-light core.
- [x] Record the rerank decision in the per-candidate selection trace.
- [x] Order the selection by the rerank decision.
- [x] Add `RerankPolicy` with enabled / family / top_n / timeout / fallback.
- [x] Resolve the policy in the multi-stage service; make the query override
      optional.
- [x] Expose the per-query override in the MCP retrieval tools and their
      schemas.
- [x] Carry the policy through the retrieval settings and the runtime
      configuration.
- [x] Degrade a failing reranker in the legacy path as well.
- [x] Make the reranker modality-aware and carry the media marker through
      indexing and retrieval.
- [x] Regression tests: the rerank decision survives the selection, the
      retrieval score is preserved, the trace records the decision, the
      policy is honoured and overridable, both paths degrade, a media
      candidate is not demoted.

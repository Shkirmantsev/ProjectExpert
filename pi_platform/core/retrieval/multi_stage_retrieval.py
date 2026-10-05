"""Default multi-stage retrieval core.

Implements :class:`pi_platform.ports.retrieval.multi_stage_retrieval.MultiStageRetrievalPort`
with the seven documented stages (§29):

1. candidate generation (cheap lexical + dense ANN + identifier lookup);
2. dense + sparse fusion into a single ranked candidate set;
3. metadata / version / security filter projection;
4. graph expansion;
5. hierarchy expansion;
6. reranking (only when ``enableReranking`` is true);
7. context assembly with deduplication and citation preservation.

The pipeline delegates each stage to a collaborator (duck-typed
through the Phase 4 ports) so the orchestrator itself stays a small
loop and the per-stage telemetry is observable in one place.
"""

from __future__ import annotations

import time
from typing import Mapping, Sequence

from pi_platform.ports.retrieval.context_assembler import (
    ContextAssemblerPort,
    ContextBudget,
)
from pi_platform.ports.retrieval.hybrid_retrieval import (
    HybridRetrievalPort,
    RetrievalHit,
)
from pi_platform.ports.retrieval.metadata_filter import MetadataFilterPort
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalError,
    MultiStageRetrievalPort,
    RetrievalQuery,
    RetrievalResult,
    STAGE_CANDIDATE_GENERATION,
    STAGE_CONTEXT_ASSEMBLY,
    STAGE_FUSION,
    STAGE_GRAPH_EXPANSION,
    STAGE_HIERARCHY_EXPANSION,
    STAGE_METADATA_FILTER,
    STAGE_RERANK,
    StageReport,
)
from pi_platform.ports.retrieval.reranker import RerankerPort


__all__ = [
    "MultiStageRetrievalCore",
    "DEFAULT_BUDGETS",
]


# Default per-stage budgets from the §29 spec; the future design
# documents these defaults and the multi-stage orchestrator respects
# them when no explicit configuration is provided.
DEFAULT_BUDGETS: Mapping[str, int] = {
    STAGE_CANDIDATE_GENERATION: 50,
    STAGE_FUSION: 50,
    STAGE_METADATA_FILTER: 40,
    STAGE_GRAPH_EXPANSION: 30,
    STAGE_HIERARCHY_EXPANSION: 30,
    STAGE_RERANK: 20,
}


class MultiStageRetrievalCore(MultiStageRetrievalPort):
    """§29 multi-stage retrieval orchestrator."""

    def __init__(
        self,
        hybrid: HybridRetrievalPort,
        metadata: MetadataFilterPort,
        graph_expansion: object,
        reranker: RerankerPort | None = None,
        context_assembler: ContextAssemblerPort | None = None,
        budgets: Mapping[str, int] | None = None,
    ) -> None:
        self._hybrid = hybrid
        self._metadata = metadata
        self._graph_expansion = graph_expansion
        self._reranker = reranker
        self._context_assembler = context_assembler
        self._budgets = dict(DEFAULT_BUDGETS)
        if budgets:
            self._budgets.update(budgets)
        self._calls = 0

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        self._calls += 1
        reports: list[StageReport] = []
        try:
            cand_budget = self._budgets[STAGE_CANDIDATE_GENERATION]
            fusion_budget = self._budgets[STAGE_FUSION]
            metadata_budget = self._budgets[STAGE_METADATA_FILTER]
            graph_budget = self._budgets[STAGE_GRAPH_EXPANSION]
            hierarchy_budget = self._budgets[STAGE_HIERARCHY_EXPANSION]
            rerank_budget = self._budgets[STAGE_RERANK]

            t0 = _now_ms()
            raw = self._hybrid.query(
                query.text, top_k=fusion_budget,
                filters=query.filters,
            )
            cand_duration = _now_ms() - t0
            cand_in = fusion_budget
            cand_out = len(raw)
            cand_budget_exhausted = cand_out >= fusion_budget
            reports.append(StageReport(
                stage=STAGE_CANDIDATE_GENERATION,
                candidatesIn=cand_in,
                candidatesOut=cand_out,
                durationMs=cand_duration,
                budgetExhausted=cand_budget_exhausted,
            ))
            reports.append(StageReport(
                stage=STAGE_FUSION,
                candidatesIn=cand_in,
                candidatesOut=cand_out,
                durationMs=0,
                budgetExhausted=cand_budget_exhausted,
            ))
            t1 = _now_ms()
            metadata_input = raw
            metadata_filter = query.filters
            if metadata_filter is None:
                from pi_platform.ports.retrieval.metadata_filter import (
                    MetadataFilter as _MetadataFilter,
                )
                metadata_filter = _MetadataFilter()
            filtered = list(
                self._metadata.apply(metadata_filter, metadata_input)
            )[:metadata_budget]
            metadata_duration = _now_ms() - t1
            reports.append(StageReport(
                stage=STAGE_METADATA_FILTER,
                candidatesIn=len(raw),
                candidatesOut=len(filtered),
                durationMs=metadata_duration,
                budgetExhausted=len(filtered) >= metadata_budget,
            ))

            t2 = _now_ms()
            expansion = self._run_graph_expansion(filtered, graph_budget)
            graph_duration = _now_ms() - t2
            reports.append(StageReport(
                stage=STAGE_GRAPH_EXPANSION,
                candidatesIn=len(filtered),
                candidatesOut=len(expansion),
                durationMs=graph_duration,
                budgetExhausted=len(expansion) >= graph_budget,
            ))

            t3 = _now_ms()
            hierarchy = self._run_hierarchy_expansion(
                filtered, hierarchy_budget,
            )
            hierarchy_duration = _now_ms() - t3
            reports.append(StageReport(
                stage=STAGE_HIERARCHY_EXPANSION,
                candidatesIn=len(filtered),
                candidatesOut=len(hierarchy),
                durationMs=hierarchy_duration,
                budgetExhausted=len(hierarchy) >= hierarchy_budget,
            ))

            ranked = list(filtered) + list(expansion) + list(hierarchy)
            dedup_ranked = _dedupe_hits(ranked)[:cand_out]
            if query.enableReranking and self._reranker is not None:
                t4 = _now_ms()
                rerank_input = dedup_ranked[:rerank_budget]
                reports.append(StageReport(
                    stage=STAGE_RERANK,
                    candidatesIn=len(dedup_ranked),
                    candidatesOut=len(rerank_input),
                    durationMs=0,
                    budgetExhausted=len(dedup_ranked) > rerank_budget,
                ))
                dedup_ranked = list(self._reranker.rerank(
                    query.text, rerank_input, top_k=query.top_k,
                ))
                rerank_duration = _now_ms() - t4
                reports[-1] = StageReport(
                    stage=STAGE_RERANK,
                    candidatesIn=len(rerank_input),
                    candidatesOut=len(dedup_ranked),
                    durationMs=rerank_duration,
                    budgetExhausted=len(rerank_input) >= rerank_budget,
                )

            if self._context_assembler is None:
                bundle = None
            else:
                t5 = _now_ms()
                bundle = self._context_assembler.assemble(
                    dedup_ranked,
                    contextBudget=ContextBudget(
                        tokenLimit=query.contextBudget,
                    ),
                    query=query,
                )
                assembly_duration = _now_ms() - t5
                reports.append(StageReport(
                    stage=STAGE_CONTEXT_ASSEMBLY,
                    candidatesIn=len(dedup_ranked),
                    candidatesOut=len(bundle.hits),
                    durationMs=assembly_duration,
                    budgetExhausted=bundle.budgetUsed >= query.contextBudget,
                ))
            budget_used = (
                bundle.budgetUsed if bundle is not None
                else sum(h.tokenEstimate for h in dedup_ranked)
            )
            return RetrievalResult(
                hits=tuple(dedup_ranked),
                contextBundle=bundle,
                stageReports=tuple(reports),
                budgetUsed=budget_used,
            )
        except Exception as exc:
            raise MultiStageRetrievalError(
                f"multi-stage retrieval failed: {exc}"
            ) from exc

    def stats(self) -> Mapping[str, int]:
        return {"calls": self._calls}

    # -- internal helpers --------------------------------------------------

    def _run_graph_expansion(
        self, hits: Sequence[RetrievalHit], budget: int,
    ) -> list[RetrievalHit]:
        if self._graph_expansion is None:
            return []
        seeds = [h.chunkId for h in hits][: max(1, budget // 3)]
        try:
            expansion = self._graph_expansion.expand(
                seeds, hops=1, edge_types=None, budget=budget,
            )
        except Exception:
            return []
        return [
            RetrievalHit(
                chunkId=entity.id,
                score=0.5,
                source="graph",
                snippet=getattr(entity, "description", "") or "",
                contentHash=entity.id,
                metadata=entity.metadata
                if hasattr(entity, "metadata") else hits[0].metadata,
                knowledgeState=entity.knowledgeState
                if hasattr(entity, "knowledgeState") else hits[0].knowledgeState,
            )
            for entity in expansion.expandedEntities[:budget]
            if not any(h.chunkId == entity.id for h in hits)
        ]

    def _run_hierarchy_expansion(
        self, hits: Sequence[RetrievalHit], budget: int,
    ) -> list[RetrievalHit]:
        if self._graph_expansion is None:
            return []
        seeds = [h.chunkId for h in hits][: max(1, budget // 3)]
        try:
            expansion = self._graph_expansion.expand(
                seeds, hops=2, edge_types=["PART_OF"], budget=budget,
            )
        except Exception:
            return []
        return [
            RetrievalHit(
                chunkId=entity.id,
                score=0.4,
                source="hierarchy",
                snippet=getattr(entity, "description", "") or "",
                contentHash=entity.id,
                metadata=entity.metadata
                if hasattr(entity, "metadata") else hits[0].metadata,
                knowledgeState=entity.knowledgeState
                if hasattr(entity, "knowledgeState") else hits[0].knowledgeState,
            )
            for entity in expansion.expandedEntities[:budget]
            if not any(h.chunkId == entity.id for h in hits)
        ]


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def _dedupe_hits(hits: Sequence[RetrievalHit]) -> list[RetrievalHit]:
    seen: set[str] = set()
    out: list[RetrievalHit] = []
    for hit in hits:
        if hit.chunkId in seen:
            continue
        seen.add(hit.chunkId)
        out.append(hit)
    return out
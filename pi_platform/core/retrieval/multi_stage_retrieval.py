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

The v0.8 refinement (OpenSpec change
``improve-ingestion-retrieval-local-models``, Change Package A3 / A5)
adds an additive twelve-stage v2 path that runs when a selection
port, explicit query features, or an explicit trace request is
present. The v2 path reranks DIRECT candidates only, produces
:class:`SupportEvidence` (never ``RetrievalHit`` with
``source="graph"`` / ``"hierarchy"``) and may attach a
:class:`~pi_platform.core.retrieval.retrieval_trace.RetrievalTrace`.
The legacy seven-stage path stays byte-identical when none of those
inputs are provided.
"""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, Sequence

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
    STAGE_PRE_RERANK_POOL,
    STAGE_QUERY_ANALYSIS,
    STAGE_RERANK,
    STAGE_RERANK_DIRECT,
    STAGE_RESERVE_ESCALATION,
    STAGE_SELECTION,
    STAGE_SUPPORT_MARKING,
    StageReport,
)
from pi_platform.ports.retrieval.reranker import (
    RERANK_FALLBACK_FAIL,
    RerankPolicy,
    RerankerPort,
    ensure_rerank_order,
)

if TYPE_CHECKING:
    # Imported for typing only; the v2 path resolves the selection
    # port lazily so the legacy import order stays intact.
    from pi_platform.ports.retrieval.selection import SelectionPort


__all__ = [
    "MultiStageRetrievalCore",
    "DEFAULT_BUDGETS",
    "DEFAULT_PRE_RERANK_POOL",
    "SupportEvidence",
    "SUPPORT_EVIDENCE_KINDS",
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

# Default cap of the pre-rerank DIRECT candidate pool from the multi-
# stage-retrieval delta spec (`pre_rerank_pool`, default 48).
DEFAULT_PRE_RERANK_POOL = 48

# Allowed SupportEvidence kinds. Support items are context evidence,
# never ranking candidates, so they never touch ``RetrievalHit.source``.
SUPPORT_EVIDENCE_KINDS: tuple[str, ...] = (
    "graph", "hierarchy", "table", "figure",
)


@dataclass(frozen=True)
class SupportEvidence:
    """Support evidence produced by graph / hierarchy expansion.

    Change Package A3 splits support items out of
    :class:`RetrievalHit` so the reranker only ever sees DIRECT
    candidates and ``RetrievalHit.source`` never grows a ``graph`` /
    ``hierarchy`` value. The context assembler attaches support items
    to the bundle with their own ``evidence_kind``.
    """

    chunk_id: str
    snippet: str = ""
    evidence_kind: str = "graph"
    score: float = 0.0
    source_document_id: str = ""
    page: int = 0
    element_id: str = ""

    def __post_init__(self) -> None:
        if self.evidence_kind not in SUPPORT_EVIDENCE_KINDS:
            raise ValueError(
                f"SupportEvidence.evidence_kind must be one of "
                f"{SUPPORT_EVIDENCE_KINDS}, got {self.evidence_kind!r}"
            )
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(
                f"SupportEvidence.score must be in [0.0, 1.0], got "
                f"{self.score}"
            )
        if self.page < 0:
            raise ValueError(
                f"SupportEvidence.page must be non-negative, got "
                f"{self.page}"
            )


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
        selection: object = None,
        rerank_policy: RerankPolicy | None = None,
    ) -> None:
        self._hybrid = hybrid
        self._metadata = metadata
        self._graph_expansion = graph_expansion
        self._reranker = reranker
        self._context_assembler = context_assembler
        self._selection = selection
        self._rerank_policy = rerank_policy or RerankPolicy()
        self._budgets = dict(DEFAULT_BUDGETS)
        if budgets:
            self._budgets.update(budgets)
        self._calls = 0
        self._fallback_selection: object | None = None

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        self._calls += 1
        try:
            if self._v2_enabled(query):
                return self._retrieve_v2(query)
            return self._retrieve_legacy(query)
        except Exception as exc:
            raise MultiStageRetrievalError(
                f"multi-stage retrieval failed: {exc}"
            ) from exc

    def stats(self) -> Mapping[str, int]:
        return {"calls": self._calls}

    def _rerank_enabled(self, query: RetrievalQuery) -> bool:
        """Resolve whether reranking runs for this query.

        A query may carry an explicit override. When it does not, the
        operator-controllable policy decides: BM25-light reranking is
        cheap and improves precision, so it is active by default and can
        be switched off explicitly.
        """

        if query.enableReranking is None:
            return self._rerank_policy.enabled
        return bool(query.enableReranking)

    # -- legacy seven-stage path -------------------------------------------

    def _retrieve_legacy(self, query: RetrievalQuery) -> RetrievalResult:
        """Run the pre-change seven-stage pipeline byte-identically.

        Only reached when no selection port, no explicit query
        features and no trace request are present; every existing
        caller (benchmark, CLI, UI composition, MCP) takes this path.
        """
        reports: list[StageReport] = []
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
        rerank_error = ""
        if self._rerank_enabled(query) and self._reranker is not None:
            t4 = _now_ms()
            rerank_input = dedup_ranked[:rerank_budget]
            reports.append(StageReport(
                stage=STAGE_RERANK,
                candidatesIn=len(dedup_ranked),
                candidatesOut=len(rerank_input),
                durationMs=0,
                budgetExhausted=len(dedup_ranked) > rerank_budget,
            ))
            try:
                dedup_ranked = list(self._reranker.rerank(
                    query.text, rerank_input, top_k=query.top_k,
                ))
            except Exception as exc:
                # The legacy path must degrade exactly like the v2 path:
                # a failing reranker never fails the retrieval.
                if self._rerank_policy.fallback == RERANK_FALLBACK_FAIL:
                    raise
                dedup_ranked = list(rerank_input)
                rerank_error = f"{type(exc).__name__}: {exc}"
            dedup_ranked = ensure_rerank_order(dedup_ranked)
            rerank_duration = _now_ms() - t4
            reports[-1] = StageReport(
                stage=STAGE_RERANK,
                candidatesIn=len(rerank_input),
                candidatesOut=len(dedup_ranked),
                durationMs=rerank_duration,
                budgetExhausted=len(rerank_input) >= rerank_budget,
                error=rerank_error,
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

    # -- v0.8-refinement twelve-stage path ---------------------------------

    def _v2_enabled(self, query: RetrievalQuery) -> bool:
        """Whether the twelve-stage v2 path runs for ``query``.

        The v2 path is gated on additive inputs only: a selection
        port, explicit ``RetrievalQuery.query_features`` or an
        explicit ``include_trace`` request. With none of them set the
        legacy seven-stage path stays byte-identical.
        """
        return (
            self._selection is not None
            or query.query_features is not None
            or bool(query.include_trace)
        )

    def _retrieve_v2(self, query: RetrievalQuery) -> RetrievalResult:
        """Run the twelve-stage v0.8-refinement pipeline (§4.2 order).

        Rerank runs on the DIRECT pre-rerank pool only; graph /
        hierarchy expansion runs on the selected primary + protected
        seeds and yields :class:`SupportEvidence`, never
        :class:`RetrievalHit` with a ``graph`` / ``hierarchy`` source.
        """
        reports: list[StageReport] = []
        budget_decisions: list[str] = []
        fusion_budget = self._budgets[STAGE_FUSION]
        metadata_budget = self._budgets[STAGE_METADATA_FILTER]
        graph_budget = self._budgets[STAGE_GRAPH_EXPANSION]
        hierarchy_budget = self._budgets[STAGE_HIERARCHY_EXPANSION]
        pool_cap = DEFAULT_PRE_RERANK_POOL

        # a) query analysis — bookkeeping stage report.
        reports.append(StageReport(
            stage=STAGE_QUERY_ANALYSIS,
            candidatesIn=0,
            candidatesOut=0,
            durationMs=0,
        ))
        qf = (
            query.query_features if query.query_features is not None
            else self._extract_query_features(query.text)
        )

        # b) candidate generation — hybrid exact / dense / sparse with
        # the analysed query features.
        t0 = _now_ms()
        raw = self._hybrid.query(
            query.text, top_k=fusion_budget,
            filters=query.filters, query_features=qf,
        )
        cand_duration = _now_ms() - t0
        cand_out = len(raw)
        reports.append(StageReport(
            stage=STAGE_CANDIDATE_GENERATION,
            candidatesIn=max(fusion_budget, cand_out),
            candidatesOut=cand_out,
            durationMs=cand_duration,
            budgetExhausted=cand_out >= fusion_budget,
        ))

        # c) metadata / version / security filter — same projection
        # as the legacy path.
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

        # d) fusion — bookkeeping report (fusion already happened
        # inside the hybrid core's RRF / linear strategy).
        reports.append(StageReport(
            stage=STAGE_FUSION,
            candidatesIn=len(filtered),
            candidatesOut=len(filtered),
            durationMs=0,
        ))

        # e) pre-rerank pool — DIRECT candidates only, ordered by
        # (-score, chunkId) for determinism.
        pool = sorted(
            filtered, key=lambda h: (-h.score, h.chunkId),
        )[:pool_cap]
        reports.append(StageReport(
            stage=STAGE_PRE_RERANK_POOL,
            candidatesIn=len(filtered),
            candidatesOut=len(pool),
            durationMs=0,
            budgetExhausted=len(filtered) > pool_cap,
        ))
        if len(filtered) > pool_cap:
            budget_decisions.append(
                f"pre_rerank_pool_capped:{pool_cap}",
            )

        # f) rerank DIRECT candidates — never graph / hierarchy
        # support. On reranker failure fall back to the RRF pre-rerank
        # ordering and record the error in the stage report.
        rerank_error = ""
        reranked = list(pool)
        rerank_duration = 0
        if self._rerank_enabled(query) and self._reranker is not None:
            t2 = _now_ms()
            try:
                reranked = list(self._reranker.rerank(
                    query.text, pool, top_k=pool_cap,
                ))
            except Exception as exc:
                if self._rerank_policy.fallback == RERANK_FALLBACK_FAIL:
                    raise
                reranked = list(pool)
                rerank_error = f"{type(exc).__name__}: {exc}"
                budget_decisions.append("rerank_fallback_to_rrf")
            reranked = ensure_rerank_order(reranked)
            rerank_duration = _now_ms() - t2
        reports.append(StageReport(
            stage=STAGE_RERANK_DIRECT,
            candidatesIn=max(len(pool), len(reranked)),
            candidatesOut=len(reranked),
            durationMs=rerank_duration,
            budgetExhausted=len(pool) >= pool_cap,
            error=rerank_error,
        ))

        # g) selection — non-destructive PRIMARY / RESERVE / PROTECTED
        # pools with a per-candidate trace.
        t3 = _now_ms()
        selection_result = self._resolve_selection_port().select(
            candidates=reranked, query_features=qf, budget=pool_cap,
        )
        selection_duration = _now_ms() - t3
        primary = tuple(selection_result.primary)
        reserve = tuple(selection_result.reserve)
        protected = tuple(selection_result.protected)
        pool_total = len(primary) + len(reserve) + len(protected)
        reports.append(StageReport(
            stage=STAGE_SELECTION,
            candidatesIn=max(len(reranked), pool_total),
            candidatesOut=pool_total,
            durationMs=selection_duration,
            budgetExhausted=pool_total >= pool_cap,
        ))

        # h) graph expansion from the SELECTED primary + protected
        # seeds, not from the full pre-rerank pool.
        seeds = [h.chunkId for h in primary] + [
            h.chunkId for h in protected
        ]
        t4 = _now_ms()
        graph_support = self._expand_support(
            seeds, hops=1, edge_types=None, budget=graph_budget,
            evidence_kind="graph",
        )
        graph_duration = _now_ms() - t4
        reports.append(StageReport(
            stage=STAGE_GRAPH_EXPANSION,
            candidatesIn=max(len(seeds), len(graph_support)),
            candidatesOut=len(graph_support),
            durationMs=graph_duration,
            budgetExhausted=len(graph_support) >= graph_budget,
        ))

        # i) hierarchy / adjacent expansion (PART_OF, two hops).
        t5 = _now_ms()
        hierarchy_support = self._expand_support(
            seeds, hops=2, edge_types=["PART_OF"],
            budget=hierarchy_budget, evidence_kind="hierarchy",
        )
        hierarchy_duration = _now_ms() - t5
        reports.append(StageReport(
            stage=STAGE_HIERARCHY_EXPANSION,
            candidatesIn=max(len(seeds), len(hierarchy_support)),
            candidatesOut=len(hierarchy_support),
            durationMs=hierarchy_duration,
            budgetExhausted=len(hierarchy_support) >= hierarchy_budget,
        ))
        support_evidence = tuple(graph_support) + tuple(hierarchy_support)

        # j) support marking — bookkeeping stage report.
        reports.append(StageReport(
            stage=STAGE_SUPPORT_MARKING,
            candidatesIn=len(support_evidence),
            candidatesOut=len(support_evidence),
            durationMs=0,
        ))

        # k) context assembly — direct hits plus the selection result
        # and the support evidence. Unknown kwargs are filtered via
        # inspect.signature so external custom assemblers that only
        # accept the legacy parameters keep working.
        direct_hits = list(primary) + list(reserve) + list(protected)
        bundle = self._assemble_selection_aware(
            direct_hits, query, support_evidence, selection_result,
        )
        if bundle is None:
            reports.append(StageReport(
                stage=STAGE_CONTEXT_ASSEMBLY,
                candidatesIn=len(direct_hits),
                candidatesOut=0,
                durationMs=0,
            ))
        else:
            reports.append(StageReport(
                stage=STAGE_CONTEXT_ASSEMBLY,
                candidatesIn=max(len(direct_hits), len(bundle.hits)),
                candidatesOut=len(bundle.hits),
                durationMs=0,
                budgetExhausted=(
                    bundle.budgetUsed >= query.contextBudget
                ),
            ))

        # l) reserve escalation — bookkeeping stage report; the
        # escalation itself runs inside the context assembler (A4).
        reports.append(StageReport(
            stage=STAGE_RESERVE_ESCALATION,
            candidatesIn=0,
            candidatesOut=0,
            durationMs=0,
        ))

        budget_used = (
            bundle.budgetUsed if bundle is not None
            else sum(h.tokenEstimate for h in direct_hits)
        )

        # A5: build the optional retrieval trace from the data the
        # pipeline already computed (no new business logic here).
        # The trace is attached only when the caller explicitly
        # requested it via ``include_trace``; a wired selection port
        # alone never forces a trace onto the result.
        trace = None
        if bool(query.include_trace):
            trace = self._build_trace(
                query=query,
                query_features=qf,
                raw=raw,
                pool=pool,
                reranked=reranked,
                selection_result=selection_result,
                seeds=seeds,
                graph_support=graph_support,
                hierarchy_support=hierarchy_support,
                reports=reports,
                budget_decisions=budget_decisions,
                rerank_error=rerank_error,
            )

        return RetrievalResult(
            hits=tuple(direct_hits),
            contextBundle=bundle,
            stageReports=tuple(reports),
            budgetUsed=budget_used,
            trace=trace,
            primary_count=len(primary),
            reserve_count=len(reserve),
            protected_count=len(protected),
            support_count=len(support_evidence),
            selection_result=selection_result,
        )

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

    def _extract_query_features(self, text: str) -> object | None:
        """Analyse ``text`` into :class:`QueryFeatures`, if available.

        Falls back to ``None`` (legacy routing) when
        :class:`QueryFeatures` cannot be imported; never raises.
        """
        try:
            from pi_platform.core.retrieval.query_features import (
                QueryFeatures,
            )
        except Exception:
            return None
        try:
            return QueryFeatures.from_text(text)
        except Exception:
            return None

    def _resolve_selection_port(self) -> object:
        """Return the configured selection port or a lazy default.

        The fallback only matters when the v2 path runs without an
        explicitly wired selection port (explicit query features or a
        trace request); it keeps the twelve-stage order coherent.
        """
        if self._selection is not None:
            return self._selection
        if self._fallback_selection is None:
            from pi_platform.core.retrieval.selection import SelectionCore
            self._fallback_selection = SelectionCore()
        return self._fallback_selection

    def _expand_support(
        self, seeds: Sequence[str], *, hops: int,
        edge_types: object, budget: int, evidence_kind: str,
    ) -> list[SupportEvidence]:
        """Expand ``seeds`` and wrap the result as SupportEvidence.

        Never constructs a ``RetrievalHit`` with ``source="graph"``
        or ``"hierarchy"``; any failure yields an empty list instead
        of raising.
        """
        if self._graph_expansion is None or not seeds:
            return []
        limited = list(seeds)[: max(1, budget // 3)]
        try:
            expansion = self._graph_expansion.expand(
                limited, hops=hops, edge_types=edge_types, budget=budget,
            )
        except Exception:
            return []
        return self._to_support_evidence(
            expansion, evidence_kind=evidence_kind,
        )[:budget]

    def _to_support_evidence(
        self, expansion: object, evidence_kind: str,
    ) -> list[SupportEvidence]:
        """Safely convert a graph expansion result into SupportEvidence.

        Reads ``entity.id``, ``entity.description`` and
        ``entity.metadata`` defensively; any failure yields ``[]``
        instead of raising.
        """
        try:
            entities = getattr(expansion, "expandedEntities", ()) or ()
            out: list[SupportEvidence] = []
            for entity in entities:
                try:
                    chunk_id = str(getattr(entity, "id", "") or "")
                    if not chunk_id:
                        continue
                    snippet = str(
                        getattr(entity, "description", "") or "",
                    )
                    metadata = getattr(entity, "metadata", None)
                    document_id = ""
                    if metadata is not None:
                        document_id = str(
                            getattr(metadata, "documentId", "") or "",
                        )
                    out.append(SupportEvidence(
                        chunk_id=chunk_id,
                        snippet=snippet,
                        evidence_kind=evidence_kind,
                        source_document_id=document_id,
                    ))
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def _assemble_selection_aware(
        self, direct_hits: Sequence[RetrievalHit], query: RetrievalQuery,
        support_evidence: Sequence[SupportEvidence],
        selection_result: object,
    ) -> object | None:
        """Call the context assembler with the additive v2 kwargs.

        ``support_evidence`` / ``selection_result`` are only passed
        when the assembler's ``assemble`` signature accepts them; a
        custom legacy assembler keeps the pre-change call shape.
        """
        assembler = self._context_assembler
        if assembler is None:
            return None
        try:
            params = inspect.signature(assembler.assemble).parameters
        except (TypeError, ValueError):
            params = {}
        kwargs: dict[str, object] = {
            "contextBudget": ContextBudget(tokenLimit=query.contextBudget),
            "query": query,
        }
        if "support_evidence" in params:
            kwargs["support_evidence"] = tuple(support_evidence)
        if "selection_result" in params:
            kwargs["selection_result"] = selection_result
        return assembler.assemble(direct_hits, **kwargs)

    def _build_trace(
        self, *, query: RetrievalQuery, query_features: object,
        raw: Sequence[RetrievalHit], pool: Sequence[RetrievalHit],
        reranked: Sequence[RetrievalHit], selection_result: object,
        seeds: Sequence[str],
        graph_support: Sequence[SupportEvidence],
        hierarchy_support: Sequence[SupportEvidence],
        reports: Sequence[StageReport],
        budget_decisions: Sequence[str],
        rerank_error: str,
    ) -> object:
        """Assemble a RetrievalTrace from already-computed pipeline data."""
        from pi_platform.core.retrieval.retrieval_trace import (
            RetrievalTraceBuilder,
        )

        builder = RetrievalTraceBuilder()
        builder.set("query_features", query_features)
        builder.set("active_filters", query.filters)
        builder.set("exact_candidates", tuple(
            h.chunkId for h in raw if h.source == "exact"
        ))
        builder.set("dense_candidates", tuple(
            h.chunkId for h in raw if h.source in ("dense", "hybrid")
        ))
        builder.set("sparse_candidates", tuple(
            h.chunkId for h in raw if h.source in ("sparse", "hybrid")
        ))
        builder.set("fusion", {
            "strategy": getattr(
                self._hybrid, "fusion_strategy", "rrf",
            ),
            "candidates_in": len(raw),
            "candidates_out": len(raw),
            "budget": self._budgets[STAGE_FUSION],
        })
        builder.set("reranker", {
            "applied": bool(
                query.enableReranking
                and self._reranker is not None
                and not rerank_error
            ),
            "input": tuple(h.chunkId for h in pool),
            "output": tuple(h.chunkId for h in reranked),
            "error": rerank_error,
        })
        builder.set("selection", {
            "primary": tuple(
                h.chunkId for h in selection_result.primary
            ),
            "reserve": tuple(
                h.chunkId for h in selection_result.reserve
            ),
            "protected": tuple(
                h.chunkId for h in selection_result.protected
            ),
            "dropped_duplicate": tuple(
                h.chunkId for h in selection_result.dropped_duplicate
            ),
        })
        builder.set("graph_expansion", {
            "seeds": tuple(seeds),
            "evidence": tuple(s.chunk_id for s in graph_support),
            "evidence_kind": "graph",
        })
        builder.set("hierarchy_expansion", {
            "seeds": tuple(seeds),
            "evidence": tuple(s.chunk_id for s in hierarchy_support),
            "evidence_kind": "hierarchy",
        })
        for decision in budget_decisions:
            builder.add_budget_decision(decision)
        for report in reports:
            builder.add_timing(report.stage, report.durationMs)
        return builder.build()


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

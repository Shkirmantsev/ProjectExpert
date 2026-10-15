"""Multi-stage pipeline order tests (Change Package A3).

Covers the multi-stage-retrieval delta spec scenarios: the twelve-
stage v2 order, rerank running on DIRECT candidates only (support
nodes are never cross-encoded), the byte-identical legacy seven-stage
path, and the guarantee that the v2 path never constructs a
``RetrievalHit`` with ``source="graph"`` / ``"hierarchy"``.
"""

from __future__ import annotations

import unittest

from pi_platform.adapters.retrieval.context_assembler_adapter import (
    ContextAssemblerAdapter,
)
from pi_platform.adapters.retrieval.hybrid_retrieval import (
    HybridRetrievalAdapter,
)
from pi_platform.adapters.retrieval.metadata_filter_adapter import (
    MetadataFilterAdapter,
)
from pi_platform.core.canonical.value_types import (
    Entity,
    KnowledgeState,
    Metadata,
)
from pi_platform.core.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalCore,
    SupportEvidence,
)
from pi_platform.core.retrieval.selection import SelectionCore
from pi_platform.ports.retrieval.hybrid_retrieval import (
    RetrievalHit,
)
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    RetrievalQuery,
    STAGE_ORDER,
    STAGE_ORDER_V2,
)
from pi_platform.ports.runtime.graph_expansion import GraphExpansion


__all__ = [
    "SupportNotCrossEncodedTests",
    "StageOrderV2Tests",
    "LegacyPathTests",
    "NoGraphSourceHitTests",
]


_DENSE_HITS = (
    RetrievalHit(
        chunkId="c-1", score=0.95, source="dense",
        snippet="FinishPack protocol message", contentHash="h-1",
        metadata=Metadata(documentId="doc-1", version="0.0.0",
                          language="en"),
        knowledgeState=KnowledgeState.VERIFIED,
        tokenEstimate=8,
    ),
    RetrievalHit(
        chunkId="c-2", score=0.40, source="dense",
        snippet="packing protocol variant", contentHash="h-2",
        metadata=Metadata(documentId="doc-1", version="0.0.0",
                          language="en"),
        knowledgeState=KnowledgeState.VERIFIED,
        tokenEstimate=8,
    ),
)

_SPARSE_HITS = (
    RetrievalHit(
        chunkId="c-1", score=0.80, source="sparse",
        snippet="FinishPack protocol message", contentHash="h-1",
        metadata=Metadata(documentId="doc-1", version="0.0.0",
                          language="en"),
        knowledgeState=KnowledgeState.VERIFIED,
        tokenEstimate=8,
    ),
    RetrievalHit(
        chunkId="c-4", score=0.60, source="sparse",
        snippet="packing protocol variant", contentHash="h-4",
        metadata=Metadata(documentId="doc-2", version="0.0.0",
                          language="en"),
        knowledgeState=KnowledgeState.VERIFIED,
        tokenEstimate=8,
    ),
)

SUPPORT_IDS = tuple(f"sup-{i}" for i in range(5))


class _RecordingReranker:
    """Reranker stub that records the chunk ids it is asked to score."""

    def __init__(self) -> None:
        self.inputs: list[tuple[str, ...]] = []

    def rerank(self, query, candidates, *, top_k=10):
        self.inputs.append(tuple(h.chunkId for h in candidates))
        return list(candidates)[:top_k]

    def score(self, query, candidate) -> float:
        return candidate.score

    def model_version(self) -> str:
        return "stub-reranker-1"

    def license_id(self) -> str:
        return "Apache-2.0"

    def family(self) -> str:
        return "stub"

    def stats(self):
        return {"calls": len(self.inputs)}


class _EntityGraphStub:
    """Graph expansion stub that returns a fixed entity list."""

    def __init__(self, entity_ids) -> None:
        self._entity_ids = tuple(entity_ids)
        self.calls: list[dict] = []

    def expand(self, seeds, *, hops, edge_types, budget):
        self.calls.append({
            "seeds": tuple(seeds), "hops": hops,
            "edge_types": edge_types, "budget": budget,
        })
        entities = tuple(
            Entity(
                id=entity_id, family="Component", label=entity_id,
                description=f"support for {entity_id}",
                metadata=Metadata(documentId=f"support-doc-{i}",
                                  version="0.0.0", language="en"),
                knowledgeState=KnowledgeState.VERIFIED,
            )
            for i, entity_id in enumerate(self._entity_ids)
        )
        return GraphExpansion(
            seeds=tuple(seeds), expandedEntities=entities,
            expandedRelations=(), hops=hops,
            budget_exhausted=False,
        )

    def stats(self) -> dict:
        return {}


def _build_pipeline(*, selection=None, graph_entity_ids=SUPPORT_IDS,
                    reranker=None) -> MultiStageRetrievalCore:
    hybrid = HybridRetrievalAdapter(
        dense_query=lambda text, k: list(_DENSE_HITS),
        sparse_query=lambda text, k: list(_SPARSE_HITS),
    )
    return MultiStageRetrievalCore(
        hybrid=hybrid,
        metadata=MetadataFilterAdapter(),
        graph_expansion=_EntityGraphStub(graph_entity_ids),
        reranker=reranker if reranker is not None
        else _RecordingReranker(),
        context_assembler=ContextAssemblerAdapter(),
        selection=selection,
    )


def _query(**overrides) -> RetrievalQuery:
    params = {
        "text": "FinishPack protocol message ranking signal",
        "top_k": 5,
        "contextBudget": 2000,
        "enableReranking": True,
    }
    params.update(overrides)
    return RetrievalQuery(**params)


class SupportNotCrossEncodedTests(unittest.TestCase):
    """The reranker never sees graph / hierarchy support nodes."""

    def test_rerank_not_called_on_support(self):
        reranker = _RecordingReranker()
        pipeline = _build_pipeline(
            selection=SelectionCore(), reranker=reranker,
        )
        result = pipeline.retrieve(_query())
        self.assertGreaterEqual(len(reranker.inputs), 1)
        support = set(SUPPORT_IDS)
        for seen in reranker.inputs:
            self.assertEqual(set(seen) & support, set())
        # The support entities were produced, but only AFTER the
        # rerank stage, as SupportEvidence (never as rerank input).
        self.assertGreaterEqual(result.support_count, 1)


class StageOrderV2Tests(unittest.TestCase):
    """The v2 pipeline reports the twelve stages in the v2 order."""

    def test_stage_order_v2(self):
        pipeline = _build_pipeline(selection=SelectionCore())
        result = pipeline.retrieve(_query())
        stages = [r.stage for r in result.stageReports]
        self.assertEqual(stages, list(STAGE_ORDER_V2))


class LegacyPathTests(unittest.TestCase):
    """selection=None and query_features=None keep the legacy path."""

    def test_legacy_path_byte_identical(self):
        # NOTE: the legacy expansion helpers would raise on raw
        # entities because ``RetrievalHit.source`` rejects ``graph`` /
        # ``hierarchy``; that pre-change defect is preserved
        # byte-identically (the production adapter never surfaces raw
        # entities here). The stub therefore returns an id already
        # present among the direct candidates so the legacy filter
        # drops it, exactly like the pre-change pipeline.
        pipeline = _build_pipeline(
            graph_entity_ids=("c-1",),
            selection=None,
        )
        result = pipeline.retrieve(_query())
        stages = [r.stage for r in result.stageReports]
        self.assertEqual(stages, list(STAGE_ORDER))
        self.assertIsNotNone(result.contextBundle)
        # The pre-change sequence: the legacy path fuses direct
        # candidates with the graph / hierarchy expansion hits and
        # truncates back to the candidate-generation output size,
        # which for this three-candidate fixture leaves the three
        # direct candidates in their fused order.
        self.assertEqual(
            [h.chunkId for h in result.hits],
            ["c-1", "c-2", "c-4"],
        )
        # No v0.8-refinement artefacts on the legacy path.
        self.assertIsNone(result.trace)
        self.assertIsNone(result.selection_result)
        self.assertEqual(result.support_count, 0)


class NoGraphSourceHitTests(unittest.TestCase):
    """Support evidence never becomes a RetrievalHit with a graph source."""

    def test_no_retrieval_hit_with_graph_source(self):
        pipeline = _build_pipeline(selection=SelectionCore())
        result = pipeline.retrieve(_query())
        for hit in result.hits:
            self.assertNotIn(hit.source, ("graph", "hierarchy"))
        # The five stub entities per expansion stage arrive as
        # SupportEvidence instead.
        self.assertEqual(result.support_count, 10)


class SupportEvidenceTypeTests(unittest.TestCase):
    """SupportEvidence replaces the graph-source RetrievalHit."""

    def test_support_evidence_value_object(self):
        item = SupportEvidence(
            chunk_id="sup-0", snippet="support", evidence_kind="graph",
            source_document_id="doc-1",
        )
        self.assertEqual(item.chunk_id, "sup-0")
        self.assertEqual(item.evidence_kind, "graph")

    def test_support_evidence_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            SupportEvidence(chunk_id="x", evidence_kind="retrieval")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

"""Tests for the reranking policy.

The reranker's decision must survive the handover to the selection stage.
Before the fix the reranker sorted the candidates by its own score but
returned them with the OLD retrieval score, and the selection stage
re-sorted by that old score, so the rerank was silently undone.

The tests also cover the operator-controllable policy (reranking is active
by default and can be switched off), the degradation of a failing reranker
in BOTH the legacy and the v2 pipeline, and the modality-aware behaviour
that keeps a media candidate from being demoted by a text-only reranker.
"""

import unittest

from pi_platform.core.canonical.value_types import KnowledgeState, Metadata
from pi_platform.core.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalCore,
)
from pi_platform.core.retrieval.reranker import Bm25LightRerankerCore
from pi_platform.core.retrieval.query_features import QueryFeatures
from pi_platform.core.retrieval.selection import SelectionCore
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery
from pi_platform.ports.runtime.graph_expansion import GraphExpansion
from pi_platform.ports.retrieval.reranker import (
    RERANK_FALLBACK_FAIL,
    RerankPolicy,
    RerankerError,
    ensure_rerank_order,
    hit_modality,
    stamp_rerank_order,
)


def hit(chunk_id, score, snippet="", *, modality=None, document_id="doc"):
    extensions = {"media": modality} if modality else {}
    return RetrievalHit(
        chunkId=chunk_id,
        score=score,
        source="dense",
        snippet=snippet,
        contentHash="hash-" + chunk_id,
        metadata=Metadata(
            documentId=document_id,
            version="0.1.0",
            language="en",
            extensions=extensions,
        ),
        knowledgeState=KnowledgeState.VERIFIED,
    )


class FailingReranker:
    """A reranker that always fails."""

    family_name = "failing"

    def rerank(self, query, candidates, *, top_k=10):
        raise RerankerError("primary reranker timed out")

    def score(self, query, candidate):
        raise RerankerError("primary reranker timed out")

    def model_version(self):
        return "failing-1.0.0"

    def license_id(self):
        return "Apache-2.0"

    def family(self):
        return "failing"

    def stats(self):
        return {"calls": 0}


class StubHybrid:
    """A minimal hybrid retrieval port returning fixed candidates."""

    def __init__(self, hits):
        self._hits = list(hits)

    def query(self, text, *, top_k=50, dense_weight=0.5, sparse_weight=0.5,
              filters=None, query_features=None):
        return tuple(self._hits)

    def exact_id(self, identifier, *, filters=None):
        return ()

    def stats(self):
        return {"calls": 0}


class StubMetadata:
    def apply(self, metadata_filter, hits):
        return tuple(hits)

    def validate(self, metadata_filter):
        return ()

    def stats(self):
        return {"calls": 0}


class StubGraph:
    def expand(self, hits, budget=10, **kwargs):
        return GraphExpansion()

    def stats(self):
        return {"calls": 0}


def build_pipeline(hits, reranker=None, policy=None, selection="default"):
    """Build a pipeline.

    ``selection='default'`` installs the selection port, which routes the
    query to the twelve-stage v2 path. ``selection=None`` omits it, which
    routes the query to the legacy seven-stage path.
    """

    resolved = SelectionCore() if selection == "default" else selection
    return MultiStageRetrievalCore(
        hybrid=StubHybrid(hits),
        metadata=StubMetadata(),
        graph_expansion=StubGraph(),
        reranker=reranker if reranker is not None else Bm25LightRerankerCore(),
        context_assembler=None,
        selection=resolved,
        rerank_policy=policy or RerankPolicy(),
    )


class ScorePropagationTests(unittest.TestCase):
    def test_rerank_decision_survives_the_selection_stage(self):
        """The regression: a reranker that prefers B must yield B first."""

        # A has the HIGHER retrieval score but the LOWER text relevance.
        candidates = [
            hit("A", 0.030, "unrelated packaging notes"),
            hit("B", 0.025, "TCP retry implementation for the genesys service"),
        ]
        pipeline = build_pipeline(candidates)
        result = pipeline.retrieve(RetrievalQuery(text="TCP retry", top_k=2))
        order = [h.chunkId for h in result.hits]
        self.assertEqual(order[0], "B", "the rerank decision was undone by selection")

    def test_the_original_retrieval_score_is_preserved(self):
        candidates = [
            hit("A", 0.030, "unrelated packaging notes"),
            hit("B", 0.025, "TCP retry implementation"),
        ]
        reranker = Bm25LightRerankerCore()
        reranked = list(reranker.rerank("TCP retry", candidates, top_k=2))
        by_id = {h.chunkId: h for h in reranked}
        self.assertEqual(by_id["A"].score, 0.030)
        self.assertEqual(by_id["B"].score, 0.025)
        self.assertIsNotNone(by_id["B"].rerankScore)
        self.assertGreater(by_id["B"].rerankRank, 0)

    def test_the_candidate_trace_records_the_rerank_decision(self):
        candidates = [
            hit("A", 0.030, "unrelated packaging notes"),
            hit("B", 0.025, "TCP retry implementation"),
        ]
        pipeline = build_pipeline(candidates)
        result = pipeline.retrieve(
            RetrievalQuery(text="TCP retry", top_k=2, include_trace=True)
        )
        traces = {t.chunk_id: t for t in result.selection_result.traces}
        self.assertEqual(traces["B"].rerank_rank, 1)
        self.assertGreater(traces["B"].rerank_score, 0.0)
        self.assertEqual(traces["A"].rerank_rank, 2)

    def test_stamp_and_ensure_helpers(self):
        candidates = [hit("A", 0.5, "a"), hit("B", 0.4, "b")]
        stamped = stamp_rerank_order(candidates, [0.9, 0.1])
        self.assertEqual(stamped[0].rerankScore, 0.9)
        self.assertEqual(stamped[0].rerankRank, 1)
        self.assertEqual(stamped[1].rerankRank, 2)
        # A reranker that does not stamp its own scores still expresses its
        # decision through the order of the returned candidates.
        ensured = ensure_rerank_order(candidates)
        self.assertEqual([h.rerankRank for h in ensured], [1, 2])


class RerankPolicyTests(unittest.TestCase):
    def test_reranking_is_active_by_default(self):
        candidates = [
            hit("A", 0.030, "unrelated packaging notes"),
            hit("B", 0.025, "TCP retry implementation"),
        ]
        pipeline = build_pipeline(candidates)
        result = pipeline.retrieve(RetrievalQuery(text="TCP retry", top_k=2))
        self.assertEqual([h.chunkId for h in result.hits][0], "B")

    def test_reranking_can_be_switched_off(self):
        candidates = [
            hit("A", 0.030, "unrelated packaging notes"),
            hit("B", 0.025, "TCP retry implementation"),
        ]
        pipeline = build_pipeline(
            candidates, policy=RerankPolicy(enabled=False),
        )
        result = pipeline.retrieve(RetrievalQuery(text="TCP retry", top_k=2))
        self.assertEqual([h.chunkId for h in result.hits][0], "A")
        rerank_reports = [
            r for r in result.stageReports if r.stage == "rerank"
        ]
        self.assertEqual(rerank_reports, [])

    def test_a_query_can_override_the_policy(self):
        candidates = [
            hit("A", 0.030, "unrelated packaging notes"),
            hit("B", 0.025, "TCP retry implementation"),
        ]
        pipeline = build_pipeline(
            candidates, policy=RerankPolicy(enabled=False),
        )
        result = pipeline.retrieve(
            RetrievalQuery(text="TCP retry", top_k=2, enableReranking=True)
        )
        self.assertEqual([h.chunkId for h in result.hits][0], "B")

    def test_a_query_can_force_reranking_off(self):
        candidates = [
            hit("A", 0.030, "unrelated packaging notes"),
            hit("B", 0.025, "TCP retry implementation"),
        ]
        pipeline = build_pipeline(candidates)
        result = pipeline.retrieve(
            RetrievalQuery(text="TCP retry", top_k=2, enableReranking=False)
        )
        self.assertEqual([h.chunkId for h in result.hits][0], "A")

    def test_policy_validation(self):
        with self.assertRaises(ValueError):
            RerankPolicy(top_n=0)
        with self.assertRaises(ValueError):
            RerankPolicy(timeout_ms=0)
        with self.assertRaises(ValueError):
            RerankPolicy(fallback="explode")


class DegradationTests(unittest.TestCase):
    def test_a_failing_reranker_does_not_fail_the_legacy_path(self):
        candidates = [
            hit("A", 0.030, "unrelated packaging notes"),
            hit("B", 0.025, "TCP retry implementation"),
        ]
        pipeline = build_pipeline(
            candidates, reranker=FailingReranker(), policy=RerankPolicy(),
            selection=None,
        )
        result = pipeline.retrieve(RetrievalQuery(text="TCP retry", top_k=2))
        self.assertTrue(result.hits)
        # The pre-rerank (fusion) order is preserved.
        self.assertEqual([h.chunkId for h in result.hits][0], "A")
        errors = [
            r.error for r in result.stageReports if r.stage == "rerank"
        ]
        self.assertTrue(any("timed out" in error for error in errors))

    def test_a_failing_reranker_does_not_fail_the_v2_path(self):
        candidates = [
            hit("A", 0.030, "unrelated packaging notes"),
            hit("B", 0.025, "TCP retry implementation"),
        ]
        pipeline = build_pipeline(
            candidates, reranker=FailingReranker(), policy=RerankPolicy(),
        )
        result = pipeline.retrieve(
            RetrievalQuery(
                text="TCP retry", top_k=2,
                query_features=QueryFeatures.from_text("TCP retry"),
                include_trace=True,
            )
        )
        self.assertTrue(result.hits)
        errors = [
            r.error for r in result.stageReports if r.stage == "rerank_direct"
        ]
        self.assertTrue(any("timed out" in error for error in errors))

    def test_the_fail_policy_propagates_the_error(self):
        candidates = [hit("A", 0.030, "unrelated packaging notes")]
        pipeline = build_pipeline(
            candidates, reranker=FailingReranker(),
            policy=RerankPolicy(fallback=RERANK_FALLBACK_FAIL),
        )
        with self.assertRaises(Exception):
            pipeline.retrieve(RetrievalQuery(text="TCP retry", top_k=2))


class ModalityAwareTests(unittest.TestCase):
    def test_the_media_marker_is_detected(self):
        self.assertEqual(hit_modality(hit("A", 0.5, "x", modality="image")), "image")
        self.assertEqual(hit_modality(hit("A", 0.5, "x")), "text")

    def test_a_media_candidate_is_not_demoted_by_the_text_reranker(self):
        """A visually relevant image must not be pushed to the bottom
        because its textual representation does not contain the query."""

        candidates = [
            hit("IMG", 0.020, "Image: docs/architecture.png", modality="image"),
            hit("TXT", 0.030, "unrelated packaging notes"),
        ]
        reranker = Bm25LightRerankerCore()
        reranked = list(reranker.rerank("TCP retry architecture", candidates, top_k=2))
        self.assertEqual(reranked[0].chunkId, "IMG")
        self.assertEqual(reranker.stats()["media_preserved"], 1)

    def test_text_candidates_are_still_reordered_within_their_group(self):
        candidates = [
            hit("A", 0.030, "unrelated packaging notes"),
            hit("B", 0.025, "TCP retry implementation"),
        ]
        reranker = Bm25LightRerankerCore()
        reranked = list(reranker.rerank("TCP retry", candidates, top_k=2))
        self.assertEqual(reranked[0].chunkId, "B")


if __name__ == "__main__":
    unittest.main()

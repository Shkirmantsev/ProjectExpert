"""Selection model tests (Change Package A2).

Covers the retrieval-candidate-selection delta spec scenarios:
protected-hit survival, non-destructive reserve retention, PRIMARY-
only source diversity, targeted-document diversity bypass and near-
duplicate provenance preservation.
"""

from __future__ import annotations

import unittest

from pi_platform.core.canonical.value_types import KnowledgeState, Metadata
from pi_platform.core.retrieval.query_features import QueryFeatures
from pi_platform.core.retrieval.selection import SelectionCore
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.selection import (
    DEFAULT_MAX_PRIMARY_PER_SOURCE,
    DEFAULT_PRIMARY_TOP_K,
    DEFAULT_RESERVE_TOP_K,
    SelectionState,
)


def _hit(
    chunk_id: str, *, score: float, document_id: str = "DOC-0",
    content_hash: str = "", selection_state: str = "",
    snippet: str = "",
) -> RetrievalHit:
    return RetrievalHit(
        chunkId=chunk_id, score=score, source="hybrid",
        snippet=snippet, contentHash=content_hash or chunk_id,
        metadata=Metadata(
            documentId=document_id, version="0.0.0", language="en",
        ),
        knowledgeState=KnowledgeState.VERIFIED,
        tokenEstimate=8,
        selection_state=selection_state,
    )


class SelectionProtectedTests(unittest.TestCase):
    """Protected candidates survive low relevance scores."""

    def test_selection_protected_survives_low_score(self):
        qf = QueryFeatures.from_text("Where is ILO-5193 implemented?")
        protected_hit = _hit(
            "exact-ILO-5193", score=0.1,
            selection_state="PROTECTED", snippet="ILO-5193 spec",
        )
        others = [
            _hit(f"c-{i}", score=0.9 - i * 0.01) for i in range(5)
        ]
        result = SelectionCore().select(
            [protected_hit, *others], query_features=qf, budget=32,
        )
        protected_ids = {h.chunkId for h in result.protected}
        self.assertIn("exact-ILO-5193", protected_ids)
        self.assertNotIn("exact-ILO-5193",
                         {h.chunkId for h in result.primary})
        self.assertNotIn("exact-ILO-5193",
                         {h.chunkId for h in result.reserve})


class SelectionReserveTests(unittest.TestCase):
    """The reserve pool survives selection without silent loss."""

    def test_selection_reserve_pool_survives(self):
        candidates = [
            _hit(
                f"c-{i:03d}", score=0.95 - i * 0.005,
                document_id=f"DOC-{i % 10}",
            )
            for i in range(100)
        ]
        result = SelectionCore().select(
            candidates, query_features=None, budget=100,
        )
        self.assertGreaterEqual(len(result.primary), DEFAULT_PRIMARY_TOP_K)
        self.assertGreaterEqual(len(result.reserve), DEFAULT_RESERVE_TOP_K)
        # Zero silent loss: every candidate has a trace.
        traced = {t.chunk_id for t in result.traces}
        self.assertEqual(traced, {h.chunkId for h in candidates})
        self.assertEqual(len(result.protected), 0)
        self.assertEqual(len(result.dropped_duplicate), 0)


class SelectionDiversityTests(unittest.TestCase):
    """Source diversity applies to PRIMARY only."""

    def test_selection_source_diversity_primary_only(self):
        candidates = [
            _hit("a1", score=0.90, document_id="DOC-1"),
            _hit("a2", score=0.80, document_id="DOC-1"),
            _hit("a3", score=0.70, document_id="DOC-1"),
            _hit("a4", score=0.60, document_id="DOC-1"),
            _hit("a5", score=0.50, document_id="DOC-1"),
            _hit("b1", score=0.85, document_id="DOC-2"),
        ]
        result = SelectionCore().select(
            candidates, query_features=None, budget=32,
        )
        primary_doc1 = [
            h for h in result.primary
            if h.metadata.documentId == "DOC-1"
        ]
        primary_doc2 = [
            h for h in result.primary
            if h.metadata.documentId == "DOC-2"
        ]
        self.assertLessEqual(
            len(primary_doc1), DEFAULT_MAX_PRIMARY_PER_SOURCE,
        )
        self.assertEqual(len(primary_doc2), 1)
        reserve_ids = {h.chunkId for h in result.reserve}
        self.assertIn("a4", reserve_ids)
        self.assertIn("a5", reserve_ids)

    def test_selection_targeted_document_bypasses_diversity(self):
        candidates = [
            _hit("a1", score=0.90, document_id="DOC-1"),
            _hit("a2", score=0.80, document_id="DOC-1"),
            _hit("a3", score=0.70, document_id="DOC-1"),
            _hit("a4", score=0.60, document_id="DOC-1"),
            _hit("a5", score=0.50, document_id="DOC-1"),
            _hit("b1", score=0.85, document_id="DOC-2"),
        ]
        qf = QueryFeatures(target_document="DOC-1")
        result = SelectionCore().select(
            candidates, query_features=qf, budget=32,
        )
        primary_doc1 = [
            h for h in result.primary
            if h.metadata.documentId == "DOC-1"
        ]
        self.assertEqual(len(primary_doc1), 5)


class SelectionDedupTests(unittest.TestCase):
    """Near-duplicates are dropped with provenance preserved."""

    def test_selection_dedup_preserves_provenance(self):
        winner = _hit("w-1", score=0.9, content_hash="h-dup")
        loser = _hit("l-1", score=0.8, content_hash="h-dup")
        result = SelectionCore().select(
            [winner, loser], query_features=None, budget=10,
        )
        pooled_ids = (
            {h.chunkId for h in result.primary}
            | {h.chunkId for h in result.reserve}
            | {h.chunkId for h in result.protected}
        )
        self.assertIn("w-1", pooled_ids)
        self.assertNotIn("l-1", pooled_ids)
        dropped = {h.chunkId: h for h in result.dropped_duplicate}
        self.assertIn("l-1", dropped)
        trace = {t.chunk_id: t for t in result.traces}["l-1"]
        self.assertEqual(trace.selection_state,
                         SelectionState.DROPPED_DUPLICATE)
        self.assertEqual(trace.duplicate_of, "w-1")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

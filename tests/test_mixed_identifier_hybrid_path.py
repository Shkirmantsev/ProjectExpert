"""Mixed identifier + free-text hybrid path tests (Change Package A1).

Verifies that queries containing both an engineering identifier and
meaningful prose run the dense and sparse channels AND the exact
lookup, with the exact hit retained and marked
``selection_state == "PROTECTED"`` per the hybrid-retrieval delta
spec scenarios.
"""

from __future__ import annotations

import unittest

from pi_platform.core.canonical.value_types import Metadata
from pi_platform.core.retrieval.hybrid_retrieval import HybridRetrievalCore
from pi_platform.core.retrieval.query_features import QueryFeatures
from pi_platform.ports.retrieval.hybrid_retrieval import (
    HIT_SOURCE_EXACT,
    RetrievalHit,
)


class _CountingStubs:
    """Test-only dense/sparse/exact stubs that count invocations."""

    def __init__(self, exact_chunk_id: str = "chunk-exact") -> None:
        self.dense_calls = 0
        self.sparse_calls = 0
        self.exact_calls = 0
        self._exact_chunk_id = exact_chunk_id

    def dense_query(self, text: str, top_k: int) -> list[RetrievalHit]:
        self.dense_calls += 1
        return [
            RetrievalHit(
                chunkId="d-1", score=0.9, source="dense",
                snippet="semantic candidate one",
                metadata=Metadata(documentId="doc-d", version="0.0.0",
                                  language="en"),
            ),
            RetrievalHit(
                chunkId="d-2", score=0.7, source="dense",
                snippet="semantic candidate two",
                metadata=Metadata(documentId="doc-d2", version="0.0.0",
                                  language="en"),
            ),
        ]

    def sparse_query(self, text: str, top_k: int) -> list[RetrievalHit]:
        self.sparse_calls += 1
        return [
            RetrievalHit(
                chunkId="s-1", score=0.8, source="sparse",
                snippet="lexical candidate",
                metadata=Metadata(documentId="doc-s", version="0.0.0",
                                  language="en"),
            ),
        ]

    def exact_lookup(self, identifier: str) -> list[RetrievalHit]:
        self.exact_calls += 1
        return [
            RetrievalHit(
                chunkId=self._exact_chunk_id, score=1.0,
                source=HIT_SOURCE_EXACT, snippet=identifier,
                metadata=Metadata(documentId="doc-x", version="0.0.0",
                                  language="en"),
            ),
        ]


def _build_core(stubs: _CountingStubs) -> HybridRetrievalCore:
    return HybridRetrievalCore(
        dense_query=stubs.dense_query,
        sparse_query=stubs.sparse_query,
        exact_lookup=stubs.exact_lookup,
    )


class MixedIdentifierHybridPathTests(unittest.TestCase):
    """Mixed identifier + prose queries keep every channel."""

    def test_where_is_ilo_5193_runs_all_channels(self):
        text = "Where is ILO-5193 implemented?"
        stubs = _CountingStubs()
        core = _build_core(stubs)
        qf = QueryFeatures.from_text(text)
        hits = list(core.query(text, query_features=qf))
        self.assertEqual(stubs.dense_calls, 1)
        self.assertEqual(stubs.sparse_calls, 1)
        self.assertEqual(stubs.exact_calls, 1)
        exact = [h for h in hits if h.source == HIT_SOURCE_EXACT]
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0].selection_state, "PROTECTED")

    def test_mixed_query_returns_semantic_candidates_too(self):
        text = "Where is ILO-5193 implemented?"
        stubs = _CountingStubs()
        core = _build_core(stubs)
        qf = QueryFeatures.from_text(text)
        hits = list(core.query(text, query_features=qf))
        ids = {h.chunkId for h in hits}
        self.assertIn("chunk-exact", ids)
        self.assertIn("d-1", ids)
        self.assertIn("s-1", ids)

    def test_explain_psb_finish_pack_timeout_runs_all_channels(self):
        text = "Explain PSB_FINISH_PACK timeout behavior"
        stubs = _CountingStubs()
        core = _build_core(stubs)
        qf = QueryFeatures.from_text(text)
        hits = list(core.query(text, query_features=qf))
        self.assertEqual(stubs.dense_calls, 1)
        self.assertEqual(stubs.sparse_calls, 1)
        self.assertEqual(stubs.exact_calls, 1)
        exact = [h for h in hits if h.source == HIT_SOURCE_EXACT]
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0].selection_state, "PROTECTED")

    def test_gen_version_finish_pack_runs_all_channels(self):
        text = "GEN_3.0.03 FinishPack"
        stubs = _CountingStubs()
        core = _build_core(stubs)
        qf = QueryFeatures.from_text(text)
        hits = list(core.query(text, query_features=qf))
        self.assertEqual(stubs.dense_calls, 1)
        self.assertEqual(stubs.sparse_calls, 1)
        self.assertEqual(stubs.exact_calls, 1)
        exact = [h for h in hits if h.source == HIT_SOURCE_EXACT]
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0].selection_state, "PROTECTED")

    def test_protected_extractor_overrides_protected_set(self):
        text = "Where is ILO-5193 implemented?"
        stubs = _CountingStubs()
        core = HybridRetrievalCore(
            dense_query=stubs.dense_query,
            sparse_query=stubs.sparse_query,
            exact_lookup=stubs.exact_lookup,
            protected_extractor=lambda qf: frozenset({"d-1"}),
        )
        qf = QueryFeatures.from_text(text)
        hits = list(core.query(text, query_features=qf))
        by_id = {h.chunkId: h for h in hits}
        self.assertEqual(by_id["d-1"].selection_state, "PROTECTED")
        self.assertEqual(by_id["chunk-exact"].selection_state, "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

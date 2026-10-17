"""Pure-identifier fast-path tests (Change Package A1).

Verifies that a query consisting of only an engineering identifier
routes to the exact lookup only — no dense or sparse call is made —
both on the legacy path (no ``query_features`` argument, byte-
identical behaviour) and on the explicit ``QueryFeatures`` path from
the hybrid-retrieval delta spec.
"""

from __future__ import annotations

import unittest

from pi_platform.core.retrieval.hybrid_retrieval import HybridRetrievalCore
from pi_platform.core.retrieval.query_features import QueryFeatures
from pi_platform.core.canonical.value_types import Metadata
from pi_platform.ports.retrieval.hybrid_retrieval import (
    HIT_SOURCE_EXACT,
    RetrievalHit,
)


class _CountingStubs:
    """Test-only dense/sparse/exact stubs that count invocations."""

    def __init__(self) -> None:
        self.dense_calls = 0
        self.sparse_calls = 0
        self.exact_calls = 0

    def dense_query(self, text: str, top_k: int) -> list[RetrievalHit]:
        self.dense_calls += 1
        return [
            RetrievalHit(
                chunkId="d-1", score=0.9, source="dense",
                metadata=Metadata(documentId="doc-d", version="0.0.0",
                                  language="en"),
            ),
        ]

    def sparse_query(self, text: str, top_k: int) -> list[RetrievalHit]:
        self.sparse_calls += 1
        return [
            RetrievalHit(
                chunkId="s-1", score=0.8, source="sparse",
                metadata=Metadata(documentId="doc-s", version="0.0.0",
                                  language="en"),
            ),
        ]

    def exact_lookup(self, identifier: str) -> list[RetrievalHit]:
        self.exact_calls += 1
        return [
            RetrievalHit(
                chunkId=f"exact-{identifier}", score=1.0,
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


class PureIdentifierFastPathTests(unittest.TestCase):
    """``"ILO-5193"`` must never reach the semantic channels."""

    def test_legacy_path_without_query_features_skips_semantic(self):
        stubs = _CountingStubs()
        core = _build_core(stubs)
        hits = list(core.query("ILO-5193"))
        self.assertEqual(stubs.dense_calls, 0)
        self.assertEqual(stubs.sparse_calls, 0)
        self.assertEqual(stubs.exact_calls, 1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].source, HIT_SOURCE_EXACT)
        self.assertEqual(hits[0].selection_state, "")

    def test_explicit_query_features_skips_semantic(self):
        stubs = _CountingStubs()
        core = _build_core(stubs)
        qf = QueryFeatures.from_text("ILO-5193")
        hits = list(core.query("ILO-5193", query_features=qf))
        self.assertEqual(stubs.dense_calls, 0)
        self.assertEqual(stubs.sparse_calls, 0)
        self.assertEqual(stubs.exact_calls, 1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].source, HIT_SOURCE_EXACT)

    def test_pure_identifier_does_not_mark_protected(self):
        stubs = _CountingStubs()
        core = _build_core(stubs)
        qf = QueryFeatures.from_text("ILO-5193")
        hits = list(core.query("ILO-5193", query_features=qf))
        self.assertEqual(hits[0].selection_state, "")

    def test_stats_counts_exact_only(self):
        stubs = _CountingStubs()
        core = _build_core(stubs)
        core.query("PSB_FINISH_PACK")
        stats = core.stats()
        self.assertEqual(stats["dense_calls"], 0)
        self.assertEqual(stats["sparse_calls"], 0)
        self.assertEqual(stats["exact_calls"], 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

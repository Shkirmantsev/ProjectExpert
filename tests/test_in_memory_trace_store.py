"""In-memory retrieval trace store unit tests.

Package I3 of the v0.8 refinement (``improve-ingestion-
retrieval-local-models``) adds a backing store for the
debug-only ``project.get_retrieval_trace`` MCP tool. The
default adapter is :class:`InMemoryRetrievalTraceStore`; this
module pins the adapter-level behaviour (FIFO capacity, stats,
id derivation) separately from the MCP integration tests
(``tests/test_mcp_trace_tool.py``) so the port / adapter can
land in a commit on its own.
"""

from __future__ import annotations

import unittest

from pi_platform.adapters.retrieval.in_memory_trace_store import (
    InMemoryRetrievalTraceStore,
    compute_trace_id,
)
from pi_platform.core.retrieval.retrieval_trace import RetrievalTrace
from pi_platform.ports.retrieval.trace_store import RetrievalTraceRecord


__all__ = ["InMemoryTraceStoreTests"]


class InMemoryTraceStoreTests(unittest.TestCase):

    def test_in_memory_trace_store_respects_capacity(self) -> None:
        store = InMemoryRetrievalTraceStore(capacity=2)
        store.store(RetrievalTraceRecord(
            trace_id="id-x", query_text="q", trace=RetrievalTrace(),
        ))
        store.store(RetrievalTraceRecord(
            trace_id="id-y", query_text="q", trace=RetrievalTrace(),
        ))
        store.store(RetrievalTraceRecord(
            trace_id="id-z", query_text="q", trace=RetrievalTrace(),
        ))
        self.assertEqual(store.stats()["stored"], 2)
        self.assertEqual(store.stats()["evictions"], 1)

    def test_in_memory_trace_store_rejects_non_positive_capacity(self) -> None:
        with self.assertRaises(ValueError):
            InMemoryRetrievalTraceStore(capacity=0)
        with self.assertRaises(ValueError):
            InMemoryRetrievalTraceStore(capacity=-1)

    def test_in_memory_trace_store_evict_returns_status(self) -> None:
        store = InMemoryRetrievalTraceStore()
        store.store(RetrievalTraceRecord(
            trace_id="id-a", query_text="q", trace=RetrievalTrace(),
        ))
        self.assertTrue(store.evict("id-a"))
        self.assertFalse(store.evict("id-a"))
        self.assertIsNone(store.fetch("id-a"))

    def test_in_memory_trace_store_default_capacity_is_documented(self) -> None:
        from pi_platform.ports.retrieval.trace_store import (
            DEFAULT_TRACE_STORE_LIMIT,
        )
        self.assertGreater(DEFAULT_TRACE_STORE_LIMIT, 0)
        self.assertEqual(
            InMemoryRetrievalTraceStore().capacity,
            DEFAULT_TRACE_STORE_LIMIT,
        )

    def test_compute_trace_id_is_deterministic(self) -> None:
        trace = RetrievalTrace(
            dense_candidates=("c1", "c2"),
            timings=(("rerank", 5),),
        )
        first = compute_trace_id("hello", trace)
        second = compute_trace_id("hello", trace)
        self.assertEqual(first, second)
        different = compute_trace_id("world", trace)
        self.assertNotEqual(first, different)

    def test_compute_trace_id_is_hex_string(self) -> None:
        trace = RetrievalTrace()
        trace_id = compute_trace_id("any", trace)
        self.assertEqual(len(trace_id), 64)
        int(trace_id, 16)  # must parse as hex


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
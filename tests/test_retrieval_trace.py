"""Retrieval trace tests (Change Package A5).

Covers the retrieval-trace delta spec scenarios: deterministic JSON
round-trip, secret redaction (with a visible warning when the secret
provider is unavailable), optionality by default, presence when
``include_trace=True`` and per-stage timings aggregation.
"""

from __future__ import annotations

import json
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
from pi_platform.core.canonical.value_types import KnowledgeState, Metadata
from pi_platform.core.retrieval import retrieval_trace as _retrieval_trace_mod
from pi_platform.core.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalCore,
)
from pi_platform.core.retrieval.retrieval_trace import (
    RetrievalTrace,
    RetrievalTraceBuilder,
)
from pi_platform.core.retrieval.selection import SelectionCore
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.metadata_filter import MetadataFilter
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    RetrievalQuery,
    STAGE_ORDER_V2,
)


__all__ = [
    "TraceSerialisationTests",
    "TracePipelineTests",
]


SECRET = "sk-test-secret-12345"


def _provider_available() -> bool:
    return _retrieval_trace_mod._SECRET_PROVIDER is not None


def _register_secret(secret: str) -> None:
    """Register ``secret`` with the module-level provider so redaction sees it.

    ``DefaultSecretProvider.redact`` only rewrites previously resolved
    secret values; the test therefore registers a one-shot backend and
    resolves the value into the shared cache before serialising.
    """
    provider = _retrieval_trace_mod._SECRET_PROVIDER
    if provider is None:
        return
    backend_name = "retrieval-trace-test"
    provider.register_backend(backend_name, lambda ref: secret)
    reference = provider.parse(f"secret://{backend_name}/api-key")
    provider.resolve(reference)


def _hit(chunk_id: str, *, score: float, source: str = "dense",
         document_id: str = "DOC-0") -> RetrievalHit:
    return RetrievalHit(
        chunkId=chunk_id, score=score, source=source,
        snippet=f"body of {chunk_id}",
        contentHash=chunk_id,
        metadata=Metadata(
            documentId=document_id, version="0.0.0", language="en",
        ),
        knowledgeState=KnowledgeState.VERIFIED,
        tokenEstimate=4,
    )


class TraceSerialisationTests(unittest.TestCase):
    """RetrievalTrace serialises deterministically to JSON."""

    def test_trace_round_trips_through_json(self):
        builder = RetrievalTraceBuilder()
        builder.set("query_features", {"identifiers": ["ILO-5193"]})
        builder.set("active_filters", {"language": "en"})
        builder.set("exact_candidates", ("e-1", "e-2"))
        builder.set("dense_candidates", ("d-1",))
        builder.set("sparse_candidates", ("s-1",))
        builder.set("fusion", {"strategy": "rrf", "count": 3})
        builder.set("reranker", {"applied": False, "error": ""})
        builder.set("selection", {"primary": ("p-1",), "reserve": ()})
        builder.set("graph_expansion", {"evidence": ("sup-1",)})
        builder.set("hierarchy_expansion", {"evidence": ()})
        builder.add_budget_decision("pre_rerank_pool_capped:48")
        builder.add_timing("fusion", 3)
        builder.add_timing("fusion", 2)  # aggregated per stage → 5
        builder.add_timing("selection", 1)
        trace = builder.build()
        self.assertIsInstance(trace, RetrievalTrace)
        self.assertEqual(trace.exact_candidates, ("e-1", "e-2"))
        self.assertEqual(
            trace.timings, (("fusion", 5), ("selection", 1)),
        )

        payload = json.loads(builder.to_json())
        for field_name in (
            "query_features", "active_filters", "exact_candidates",
            "dense_candidates", "sparse_candidates", "fusion",
            "reranker", "selection", "graph_expansion",
            "hierarchy_expansion", "budget_decisions", "timings",
        ):
            self.assertIn(field_name, payload)
        self.assertEqual(payload["exact_candidates"], ["e-1", "e-2"])
        self.assertEqual(payload["dense_candidates"], ["d-1"])
        self.assertEqual(payload["sparse_candidates"], ["s-1"])
        self.assertEqual(payload["timings"], [["fusion", 5],
                                              ["selection", 1]])
        self.assertEqual(payload["fusion"]["strategy"], "rrf")
        # Byte-stable output: two serialisations are identical.
        self.assertEqual(builder.to_json(), builder.to_json())

    def test_trace_redacts_secret(self):
        """The serialised trace never contains a resolved secret value.

        When the module-level secret provider is available the secret
        is registered into its cache and the assertion is unconditional:
        the serialised JSON must not contain the secret string. When
        the provider is genuinely unavailable the serialiser records a
        visible ``WARNING`` budget decision instead.
        """
        _register_secret(SECRET)
        builder = RetrievalTraceBuilder()
        builder.set("query_features", {
            "identifiers": (),
            "extensions": {"api_key": SECRET},
        })
        builder.set("exact_candidates", ())
        json_text = builder.to_json()
        if _provider_available():
            self.assertNotIn(SECRET, json_text)
        else:  # pragma: no cover - defensive fallback path
            payload = json.loads(json_text)
            self.assertIn(
                "WARNING: secret_provider unavailable",
                payload["budget_decisions"],
            )

    def test_trace_redacts_secret_in_nested_dict(self):
        """Secrets nested under query_features.extensions are redacted."""
        _register_secret(SECRET)
        builder = RetrievalTraceBuilder()
        builder.set("query_features", {
            "identifiers": (),
            "extensions": {"nested": {"api_key": f"prefix-{SECRET}-suffix"}},
        })
        builder.set("exact_candidates", ())
        json_text = builder.to_json()
        if _provider_available():
            self.assertNotIn(SECRET, json_text)
        else:  # pragma: no cover - defensive fallback path
            payload = json.loads(json_text)
            self.assertIn(
                "WARNING: secret_provider unavailable",
                payload["budget_decisions"],
            )

    def test_trace_redacts_secret_in_list(self):
        """Secret strings inside a list are redacted leaf-by-leaf."""
        _register_secret(SECRET)
        builder = RetrievalTraceBuilder()
        builder.set("query_features", {
            "identifiers": (),
            "extensions": {"keys": [SECRET, "harmless"]},
        })
        builder.set("exact_candidates", ())
        json_text = builder.to_json()
        if _provider_available():
            self.assertNotIn(SECRET, json_text)
        else:  # pragma: no cover - defensive fallback path
            payload = json.loads(json_text)
            self.assertIn(
                "WARNING: secret_provider unavailable",
                payload["budget_decisions"],
            )


class TracePipelineTests(unittest.TestCase):
    """The multi-stage pipeline attaches the trace on demand."""

    def _build_pipeline(
        self, *, graph_returns_entities: bool = True,
    ) -> MultiStageRetrievalCore:
        dense_hits = [
            _hit(f"c-{i:03d}", score=0.9 - i * 0.01,
                 document_id=f"DOC-{i % 10}")
            for i in range(50)
        ]
        sparse_hits = [
            _hit(f"c-{i:03d}", score=0.5, source="sparse",
                 document_id=f"DOC-{i % 10}")
            for i in range(20, 50)
        ]
        exact_hits = [
            _hit("exact-ILO-5193", score=1.0, source="exact"),
        ]

        def exact_lookup(identifier: str):
            return [
                h for h in exact_hits if identifier in h.chunkId
            ]

        hybrid = HybridRetrievalAdapter(
            dense_query=lambda text, k: list(dense_hits),
            sparse_query=lambda text, k: list(sparse_hits),
            exact_lookup=exact_lookup,
        )

        class _GraphStub:
            def expand(self, seeds, *, hops, edge_types, budget):
                from pi_platform.core.canonical.value_types import Entity
                from pi_platform.ports.runtime.graph_expansion import (
                    GraphExpansion,
                )
                if not graph_returns_entities:
                    # The legacy path would raise on raw entities
                    # (RetrievalHit.source rejects "graph"); keep the
                    # legacy fixture clean, like the production adapter.
                    return GraphExpansion(
                        seeds=tuple(seeds), expandedEntities=(),
                        expandedRelations=(), hops=hops,
                    )
                entities = tuple(
                    Entity(
                        id=f"sup-{i}", family="Component",
                        label=f"sup-{i}",
                        description=f"support {i}",
                        metadata=Metadata(documentId=f"SUP-{i}",
                                          version="0.0.0",
                                          language="en"),
                        knowledgeState=KnowledgeState.VERIFIED,
                    )
                    for i in range(5)
                )
                return GraphExpansion(
                    seeds=tuple(seeds), expandedEntities=entities,
                    expandedRelations=(), hops=hops,
                )

            def stats(self):
                return {}

        class _StubReranker:
            def rerank(self, query, candidates, *, top_k=10):
                return list(candidates)[:top_k]

            def score(self, query, candidate):
                return candidate.score

            def model_version(self):
                return "stub-1"

            def license_id(self):
                return "Apache-2.0"

            def family(self):
                return "stub"

            def stats(self):
                return {}

        return MultiStageRetrievalCore(
            hybrid=hybrid,
            metadata=MetadataFilterAdapter(),
            graph_expansion=_GraphStub(),
            reranker=_StubReranker(),
            context_assembler=ContextAssemblerAdapter(),
            selection=SelectionCore(),
            # Raise the metadata budget above the pre-rerank pool cap
            # so the pipeline records a budget decision.
            budgets={"metadata_filter": 60},
        )

    def _trace_query(self, **overrides) -> RetrievalQuery:
        params = {
            "text": "FinishPack protocol ranking signal ILO-5193",
            "top_k": 10,
            "contextBudget": 2000,
            "enableReranking": True,
            "include_trace": True,
            "filters": MetadataFilter(),
        }
        params.update(overrides)
        return RetrievalQuery(**params)

    def test_trace_omitted_by_default(self):
        pipeline = self._build_pipeline(graph_returns_entities=False)
        # include_trace defaults to False; a wired selection port alone
        # must never force a trace onto the result.
        result = pipeline.retrieve(self._trace_query(
            include_trace=False, query_features=None,
        ))
        self.assertIsNone(result.trace)

    def test_trace_attached_when_include_trace_true_with_selection(self):
        pipeline = self._build_pipeline()
        result = pipeline.retrieve(self._trace_query(include_trace=True))
        self.assertIsNotNone(result.trace)
        self.assertIsInstance(result.trace, RetrievalTrace)

    def test_trace_present_when_include_trace_true(self):
        pipeline = self._build_pipeline()
        result = pipeline.retrieve(self._trace_query())
        trace = result.trace
        self.assertIsInstance(trace, RetrievalTrace)
        self.assertIsNotNone(trace.query_features)
        self.assertTrue(trace.query_features.identifiers)
        self.assertIsNotNone(trace.active_filters)
        self.assertTrue(trace.exact_candidates)
        self.assertTrue(trace.dense_candidates)
        self.assertTrue(trace.sparse_candidates)
        self.assertTrue(trace.fusion)
        self.assertTrue(trace.reranker)
        self.assertTrue(trace.selection)
        self.assertTrue(trace.graph_expansion)
        self.assertTrue(trace.hierarchy_expansion)
        self.assertTrue(trace.budget_decisions)
        self.assertTrue(trace.timings)

    def test_timings_present(self):
        pipeline = self._build_pipeline()
        result = pipeline.retrieve(self._trace_query())
        trace = result.trace
        timing_stages = [stage for stage, _ in trace.timings]
        self.assertEqual(
            sorted(timing_stages), sorted(set(STAGE_ORDER_V2)),
        )
        timing_map = dict(trace.timings)
        for report in result.stageReports:
            self.assertIn(report.stage, timing_map)
            self.assertGreaterEqual(timing_map[report.stage], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

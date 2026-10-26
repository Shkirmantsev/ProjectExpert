"""Wiring tests for the v0.8 refinement (OpenSpec change
``improve-ingestion-retrieval-local-models``).

These tests verify that the new ports / cores introduced by
Packages A, B and C are actually wired into the production
composition paths, not just declared and unit-tested. They
are intentionally light: each test is a smoke check on the
public surface, so a regression in the production wiring is
caught without depending on the full pipeline behaviour.
"""

from __future__ import annotations

import importlib
import inspect
import unittest


class HybridRetrievalPortQuerySignatureTests(unittest.TestCase):
    """MINOR-1: ``HybridRetrievalPort.query`` declares
    ``query_features`` so third-party implementations don't
    raise ``TypeError`` when the v2 path passes it."""

    def test_query_features_in_signature(self) -> None:
        from pi_platform.ports.retrieval.hybrid_retrieval import (
            HybridRetrievalPort,
        )

        sig = inspect.signature(HybridRetrievalPort.query)
        self.assertIn("query_features", sig.parameters)
        self.assertIs(sig.parameters["query_features"].default, None)


class CompositionWiringTests(unittest.TestCase):
    """MAJOR-3a: ``pi_platform/adapters/ui/composition.py``
    wires a ``SelectionCore`` into the multi-stage core."""

    def test_composition_references_selection_core(self) -> None:
        import tempfile
        from pathlib import Path
        from pi_platform.core.orchestration.retrieval_composition import build_production_retrieval_runtime
        from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery
        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_production_retrieval_runtime(
                cache_root=Path(tmp), startup_profile="minimal", embedding_alias="hashing",
            )
            result = runtime.multi_stage_retrieval.retrieve(RetrievalQuery(text="example", include_trace=True))
        stages = {report.stage for report in result.stageReports}
        self.assertIn("selection", stages)
        self.assertIn("query_analysis", stages)


class PipelineDriverWiringTests(unittest.TestCase):
    """MAJOR-3b: ``pi_platform/adapters/ingest/local_pipeline_driver.py``
    wires ``TokenBudgetNormalizer`` and the retrieval-text builder."""

    def test_driver_references_token_budget_normalizer(self) -> None:
        import pi_platform.adapters.ingest.local_pipeline_driver as driver
        source = inspect.getsource(driver)
        self.assertIn("TokenBudgetNormalizer", source)

    def test_driver_references_retrieval_text_builder(self) -> None:
        import pi_platform.adapters.ingest.local_pipeline_driver as driver
        source = inspect.getsource(driver)
        self.assertIn("RetrievalText", source)
        self.assertIn("retrieval_text", source)


class CLIStatusPayloadTests(unittest.TestCase):
    """MAJOR-3c: ``pi_platform/cli/main.py`` reports the v2
    selection core in the retrieval status payload."""

    def test_cli_references_selection_core_class(self) -> None:
        import pi_platform.cli.main as main
        source = inspect.getsource(main)
        self.assertIn("SelectionCore", source)
        self.assertIn("selection_default_primary_top_k", source)


class LocalContextualizerStrategyVersionTests(unittest.TestCase):
    """MINOR-2: ``LocalContextualizer.cache_key`` includes
    ``enrichment_strategy_version``."""

    def test_cache_key_changes_with_enrichment_strategy_version(self) -> None:
        from pi_platform.core.ingest.local_contextualizer import (
            LocalContextualizer,
        )

        class _NullLLM:
            family_name = "stub"

            def complete(self, prompt, *, max_tokens=256, temperature=0.0):
                return ""

            def is_available(self) -> bool:
                return False

            def model_version(self) -> str:
                return "stub-1.0.0"

            def license_id(self) -> str:
                return "Apache-2.0"

            def family(self) -> str:
                return "stub"

            def stats(self):
                return {"calls": 0}

        llm = _NullLLM()
        chunk = type(
            "C", (), {"contentHash": "h-1", "id": "c-1", "rawText": "x"},
        )()
        a = LocalContextualizer(llm=llm, enrichment_strategy_version="v1")
        b = LocalContextualizer(llm=llm, enrichment_strategy_version="v2")
        self.assertNotEqual(a.cache_key(chunk=chunk), b.cache_key(chunk=chunk))


class RetrievalTraceImportableTest(unittest.TestCase):
    """Sanity check: the new retrieval-trace types are importable
    from their canonical modules so the lazy ``__getattr__`` in
    ``pi_platform.core.retrieval`` is wired correctly."""

    def test_imports(self) -> None:
        from pi_platform.core.retrieval import retrieval_trace as rt
        from pi_platform.core.retrieval.retrieval_trace import (
            RetrievalTrace,
            RetrievalTraceBuilder,
        )
        self.assertIsNotNone(RetrievalTrace)
        self.assertIsNotNone(RetrievalTraceBuilder)
        self.assertIsNotNone(rt)


class EmbeddingProfileImportableTest(unittest.TestCase):
    """Sanity check: the new C-package types are importable."""

    def test_imports(self) -> None:
        from pi_platform.ports.retrieval.embedding_profile import (
            EMBEDDINGGEMMA2_512,
            EMBEDDINGGEMMA2_GGUF_512,
            HASHING_DEFAULT,
            EmbeddingProfile,
            EmbeddingProfileRegistry,
        )
        self.assertEqual(
            HASHING_DEFAULT.identity() != EMBEDDINGGEMMA2_512.identity(),
            True,
        )
        self.assertEqual(
            EMBEDDINGGEMMA2_512.identity() != EMBEDDINGGEMMA2_GGUF_512.identity(),
            True,
        )
        registry = EmbeddingProfileRegistry()
        self.assertEqual(registry.default("hashing").provider, "hashing")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

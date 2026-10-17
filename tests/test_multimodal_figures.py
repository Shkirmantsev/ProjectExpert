"""Multimodal figures (Package H) tests.

Change Package H of the v0.8 refinement adds the optional
multimodal figures path. The test suite asserts:

* the figure embedding port and the STUB adapter share the
  documented contract;
* the multimodal feature flag is declared
  ``EXPERIMENTAL`` and defaults to ``DISABLED``;
* the multimodal registry's helper predicates agree with
  the registry's resolve output;
* the Tier-2 figure queries are present in the golden
  query set and the corpus chunk ids match.
"""

from __future__ import annotations

import unittest
from pathlib import Path


__all__ = ["MultimodalFiguresTests"]


ROOT = Path(__file__).resolve().parents[1]


class MultimodalFiguresTests(unittest.TestCase):

    def test_figure_embedding_stub_contract(self) -> None:
        from pi_platform.adapters.retrieval.figure_embedding_stub import (
            FigureEmbeddingModelStub,
            MULTIMODAL_PROFILE_IDENTITY,
            STUB_DIMENSION,
        )
        from pi_platform.ports.retrieval.figure_embedding_model import (
            FigureEmbeddingModelError,
            FigureEmbeddingRequest,
        )
        # Default STUB is not available; the embed call MUST
        # raise a typed error.
        stub = FigureEmbeddingModelStub()
        self.assertFalse(stub.is_available())
        with self.assertRaises(FigureEmbeddingModelError):
            stub.embed_figure(FigureEmbeddingRequest(
                figure_id="fig-1", content_hash="abc",
            ))
        # The available=True path returns a deterministic
        # vector of the documented dimension.
        live = FigureEmbeddingModelStub(available=True)
        self.assertTrue(live.is_available())
        vector = live.embed_figure(FigureEmbeddingRequest(
            figure_id="fig-1", content_hash="abc",
            text_hint="caption",
        ))
        self.assertEqual(len(vector), STUB_DIMENSION)
        # Determinism: same input → same vector.
        again = live.embed_figure(FigureEmbeddingRequest(
            figure_id="fig-1", content_hash="abc",
            text_hint="caption",
        ))
        self.assertEqual(list(vector), list(again))
        # Distinct input → distinct vector.
        different = live.embed_figure(FigureEmbeddingRequest(
            figure_id="fig-2", content_hash="def",
            text_hint="caption",
        ))
        self.assertNotEqual(list(vector), list(different))
        self.assertEqual(live.model_version(), MULTIMODAL_PROFILE_IDENTITY)
        self.assertEqual(live.license_id(), "Apache-2.0")

    def test_multimodal_flag_default_is_disabled(self) -> None:
        from pi_platform.core.control.multimodal import (
            MULTIMODAL_FIGURES_FLAG,
            build_default_multimodal_registry,
            default_multimodal_context,
            multimodal_figures_enabled,
        )
        registry = build_default_multimodal_registry()
        self.assertFalse(
            multimodal_figures_enabled(
                registry, context=default_multimodal_context(),
            ),
            "multimodal.figures must default to DISABLED",
        )
        # The flag id is the documented one.
        declarations = {fid: (state, scope) for fid, state, scope in
                        registry.list()}
        self.assertIn(MULTIMODAL_FIGURES_FLAG, declarations)
        state, scope = declarations[MULTIMODAL_FIGURES_FLAG]
        self.assertEqual(state.value, "experimental")

    def test_multimodal_flag_can_be_enabled_by_override(self) -> None:
        from pi_platform.core.control.multimodal import (
            MULTIMODAL_FIGURES_FLAG,
            build_default_multimodal_registry,
            default_multimodal_context,
            multimodal_figures_enabled,
        )
        from pi_platform.ports.control.flags import (
            FeatureFlagScope,
            FeatureFlagState,
        )
        registry = build_default_multimodal_registry()
        # Off until the operator opts in.
        self.assertFalse(
            multimodal_figures_enabled(
                registry, context=default_multimodal_context(
                    deployment_profile="default",
                ),
            ),
        )
        # Opt in through a deployment-profile override.
        registry.override(
            MULTIMODAL_FIGURES_FLAG,
            state=FeatureFlagState.ENABLED,
            scope=FeatureFlagScope.DEPLOYMENT_PROFILE,
            scope_key="default",
        )
        self.assertTrue(
            multimodal_figures_enabled(
                registry, context=default_multimodal_context(
                    deployment_profile="default",
                ),
            ),
        )

    def test_multimodal_flag_handles_missing_declaration(self) -> None:
        # A hand-rolled registry without the multimodal
        # declaration returns False (the conservative
        # off-by-default answer).
        from pi_platform.core.control.flags import (
            DefaultFeatureFlagRegistry,
        )
        from pi_platform.core.control.multimodal import (
            default_multimodal_context,
            multimodal_figures_enabled,
        )
        registry = DefaultFeatureFlagRegistry()
        self.assertFalse(
            multimodal_figures_enabled(
                registry, context=default_multimodal_context(),
            ),
        )

    def test_golden_queries_include_tier2_figure_queries(self) -> None:
        from pi_platform.core.eval.golden import load_golden_queries
        from pi_platform.core.eval.corpus_loader import load_corpus_json
        queries = load_golden_queries(
            ROOT / "evals" / "corpus" / "golden_queries.yaml",
        )
        figure_queries = [
            q for q in queries
            if "figure" in q.tags or "multimodal" in q.tags
        ]
        self.assertGreaterEqual(
            len(figure_queries), 3,
            "Change Package H expects at least 3 Tier-2 figure queries",
        )
        for q in figure_queries:
            self.assertEqual(q.tier, 2)
            self.assertIn(q.corpus, ("generated-pdf",))
        # The figure queries reference chunk ids the
        # generated-pdf sub-corpus actually carries.
        chunks = load_corpus_json(
            ROOT / "evals" / "corpus" / "generated-pdf",
        )
        chunk_ids = {c.chunk_id for c in chunks}
        for q in figure_queries:
            for chunk_id in q.ground_truth_chunk_ids:
                self.assertIn(
                    chunk_id, chunk_ids,
                    f"figure query {q.id!r} references missing "
                    f"chunk {chunk_id!r}",
                )

    def test_multimodal_profile_modality_enum_and_ui_flag_composition(self) -> None:
        import json
        from pi_platform.adapters.retrieval.figure_embedding_stub import (
            FigureEmbeddingModel,
            FigureEmbeddingModelStub,
        )
        from pi_platform.adapters.ui.composition import build_flag_registry
        from pi_platform.core.control import MULTIMODAL_FIGURES_FLAG
        from pi_platform.ports.retrieval.embedding_profile import (
            MULTIMODAL_FIGURE_512,
            EmbeddingProfileRegistry,
        )
        from pi_platform.ports.retrieval.figure_embedding_model import Modality

        self.assertIs(FigureEmbeddingModel, FigureEmbeddingModelStub)
        self.assertEqual(Modality.MULTIMODAL.value, "multimodal")
        self.assertEqual(Modality.FIGURE.value, "figure")
        reg = EmbeddingProfileRegistry()
        self.assertEqual(reg.default("multimodal"), MULTIMODAL_FIGURE_512)
        self.assertEqual(FigureEmbeddingModel().profile, MULTIMODAL_FIGURE_512)
        ui_flags = {fid for fid, _, _ in build_flag_registry().list()}
        self.assertIn(MULTIMODAL_FIGURES_FLAG, ui_flags)
        licenses_path = ROOT / "distribution" / "licenses" / "model-licenses.json"
        self.assertTrue(licenses_path.exists())
        payload = json.loads(licenses_path.read_text(encoding="utf-8"))
        model_ids = {m["model_id"] for m in payload["models"]}
        self.assertIn("multimodal-figure-512", model_ids)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
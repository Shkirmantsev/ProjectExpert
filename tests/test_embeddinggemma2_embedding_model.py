"""EmbeddingGemma 2 stub adapter tests (Change Package C1).

Tier-1 import-and-contract tests: the stub preserves the production
:class:`EmbeddingModelPort` surface (dimension, model version,
license, profile) and raises a clear ``EmbeddingModelError`` from
``embed()`` / ``embed_batch()`` because the real binding is pending.
"""

from __future__ import annotations

import unittest

from pi_platform.adapters.retrieval.embeddinggemma2_embedding_model import (
    ADAPTER_NAME,
    DEFAULT_LICENSE_ID,
    EmbeddingGemma2EmbeddingModel,
)
from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
)
from pi_platform.ports.retrieval.embedding_profile import (
    EMBEDDINGGEMMA2_512,
    EmbeddingProfile,
)


class EmbeddingGemma2EmbeddingModelTests(unittest.TestCase):
    def setUp(self):
        self.profile = EmbeddingProfile(
            provider=EMBEDDINGGEMMA2_512.provider,
            model_id=EMBEDDINGGEMMA2_512.model_id,
            model_revision=EMBEDDINGGEMMA2_512.model_revision,
            modality=EMBEDDINGGEMMA2_512.modality,
            output_dimension=EMBEDDINGGEMMA2_512.output_dimension,
            normalization=EMBEDDINGGEMMA2_512.normalization,
            instruction_profile=EMBEDDINGGEMMA2_512.instruction_profile,
            tokenizer_id=EMBEDDINGGEMMA2_512.tokenizer_id,
            strategy_version=EMBEDDINGGEMMA2_512.strategy_version,
        )
        self.model = EmbeddingGemma2EmbeddingModel(profile=self.profile)

    def test_implements_port(self):
        self.assertIsInstance(self.model, EmbeddingModelPort)

    def test_dimension_matches_profile(self):
        self.assertEqual(self.model.dimension(), self.profile.output_dimension)

    def test_model_version_returns_profile_identity(self):
        self.assertEqual(self.model.model_version(), self.profile.identity())

    def test_license_id_recorded(self):
        self.assertEqual(self.model.license_id(), DEFAULT_LICENSE_ID)
        self.assertEqual(self.model.license_id(), "Apache-2.0")

    def test_embed_raises_with_clear_message(self):
        with self.assertRaises(EmbeddingModelError) as ctx:
            self.model.embed("hi")
        message = str(ctx.exception)
        self.assertIn("not bound", message)
        self.assertIn("install", message)

    def test_embed_batch_raises_with_clear_message(self):
        with self.assertRaises(EmbeddingModelError) as ctx:
            self.model.embed_batch(["hello", "world"])
        message = str(ctx.exception)
        self.assertIn("not bound", message)
        self.assertIn("install", message)

    def test_profile_returns_same_instance(self):
        self.assertIs(self.model.profile(), self.profile)

    def test_default_constructor_uses_builtin_profile(self):
        default = EmbeddingGemma2EmbeddingModel()
        self.assertEqual(default.profile(), EMBEDDINGGEMMA2_512)
        self.assertEqual(default.dimension(), 512)

    def test_adapter_name_is_documented(self):
        self.assertEqual(ADAPTER_NAME, "embeddinggemma2")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

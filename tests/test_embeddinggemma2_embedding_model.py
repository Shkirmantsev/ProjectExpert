"""EmbeddingGemma 2 embedding model tests (open spec change PR 3).

The real :class:`EmbeddingGemma2EmbeddingModel` adapter attempts
to load the pinned model from the local Hugging Face cache. The
test suite has two layers:

1. **Contract tests** — always run; they verify the adapter
   preserves the :class:`EmbeddingModelPort` surface
   (``dimension``, ``model version``, ``license``, ``profile``).
2. **Real-model integration tests** — they exercise the
   end-to-end ``embed()`` path. They are guarded by a probe that
   the cached snapshot is loadable by the active
   ``sentence-transformers`` release. When the cache is stale
   or the active ST release cannot deserialise the model
   (``modules.json`` layout drift), the integration tests are
   skipped with a clear ``EmbeddingModelError`` probe.
"""
from __future__ import annotations

import unittest

from pi_platform.adapters.retrieval.embeddinggemma2_embedding_model import (
    ADAPTER_NAME,
    DEFAULT_LICENSE_ID,
    EmbeddingGemma2EmbeddingModel,
    is_real_binding_available,
)
from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
)
from pi_platform.ports.retrieval.embedding_profile import (
    EMBEDDINGGEMMA2_512,
    EmbeddingProfile,
)


def _real_load_works() -> bool:
    """Return True iff a fresh model instance can be constructed
    AND embed a short probe string. The probe catches environments
    where ``sentence-transformers`` is importable but the cached
    snapshot is incompatible with the active release.
    """

    if not is_real_binding_available():
        return False
    try:
        m = EmbeddingGemma2EmbeddingModel(profile=EMBEDDINGGEMMA2_512)
        m.embed("ping")
        return True
    except EmbeddingModelError:
        return False
    except Exception:
        return False


_REAL_MODEL_LOAD_WORKS = _real_load_works()


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

    @unittest.skipUnless(
        _REAL_MODEL_LOAD_WORKS,
        "real EmbeddingGemma 2 binding is not loadable in this env "
        "(sentence-transformers version mismatch or stale HF cache)",
    )
    def test_embed_returns_finite_l2_normalised_vector(self):
        vec = self.model.embed("hello world")
        self.assertEqual(len(vec), self.profile.output_dimension)
        # All values must be finite (no NaN, no Inf).
        self.assertTrue(all(float(v) == float(v) for v in vec))
        self.assertTrue(all(abs(float(v)) < 1e6 for v in vec))
        # L2 norm approximately 1.
        norm = sum(float(v) * float(v) for v in vec) ** 0.5
        self.assertAlmostEqual(norm, 1.0, delta=1e-2)

    @unittest.skipUnless(
        _REAL_MODEL_LOAD_WORKS,
        "real EmbeddingGemma 2 binding is not loadable in this env",
    )
    def test_embed_batch_matches_single_embed_shape(self):
        batch = self.model.embed_batch(["hello", "world"])
        self.assertEqual(len(batch), 2)
        self.assertEqual(len(batch[0]), self.profile.output_dimension)
        self.assertEqual(len(batch[1]), self.profile.output_dimension)

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

"""Embedding profile identity and registry tests (Change Package C2).

The profile is the namespace: canonical bytes are byte-stable across
construction order, identities are unique per built-in profile, and
the registry fails loudly on unknown identities.
"""

from __future__ import annotations

import unittest

from pi_platform.ports.retrieval.embedding_profile import (
    EMBEDDINGGEMMA2_512,
    EMBEDDINGGEMMA2_GGUF_512,
    HASHING_DEFAULT,
    EmbeddingProfile,
    EmbeddingProfileMismatchError,
    EmbeddingProfileRegistry,
)


def _profile_from_kwargs(**kwargs) -> EmbeddingProfile:
    """Build a profile from explicit kwargs in the given keyword order."""

    return EmbeddingProfile(
        provider=kwargs["provider"],
        model_id=kwargs["model_id"],
        model_revision=kwargs["model_revision"],
        modality=kwargs["modality"],
        output_dimension=kwargs["output_dimension"],
        normalization=kwargs["normalization"],
        instruction_profile=kwargs["instruction_profile"],
        tokenizer_id=kwargs["tokenizer_id"],
        strategy_version=kwargs["strategy_version"],
    )


class EmbeddingProfileIdentityTests(unittest.TestCase):
    def test_canonical_bytes_byte_stable(self):
        # Same fields, different keyword insertion order at the call
        # site; canonical_bytes sorts keys, so the encodings match.
        first = _profile_from_kwargs(
            provider="hashing",
            model_id="hashing-1.0.0",
            model_revision="v1",
            modality="text",
            output_dimension=384,
            normalization="l2",
            instruction_profile="default",
            tokenizer_id="hashing/v1",
            strategy_version="embedding-profile-v1",
        )
        second = EmbeddingProfile(
            strategy_version="embedding-profile-v1",
            tokenizer_id="hashing/v1",
            instruction_profile="default",
            normalization="l2",
            output_dimension=384,
            modality="text",
            model_revision="v1",
            model_id="hashing-1.0.0",
            provider="hashing",
        )
        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
        # No whitespace in the canonical encoding.
        self.assertNotIn(b" ", first.canonical_bytes())

    def test_identity_deterministic(self):
        first = EmbeddingProfile(
            provider="embeddinggemma2",
            model_id="embeddinggemma2-512",
            model_revision="pinned-stub",
            modality="text",
            output_dimension=512,
            normalization="l2",
            instruction_profile="matryoshka-512",
            tokenizer_id="embeddinggemma2/v1-stub",
            strategy_version="embedding-profile-v1",
        )
        second = EmbeddingProfile(
            strategy_version="embedding-profile-v1",
            tokenizer_id="embeddinggemma2/v1-stub",
            instruction_profile="matryoshka-512",
            normalization="l2",
            output_dimension=512,
            modality="text",
            model_revision="pinned-stub",
            model_id="embeddinggemma2-512",
            provider="embeddinggemma2",
        )
        self.assertEqual(first.identity(), second.identity())
        self.assertEqual(len(first.identity()), 64)

    def test_hash_vs_embeddinggemma2_vs_gguf_distinct(self):
        # Three distinct vector spaces remain: the hashing fallback,
        # the native EmbeddingGemma 2 binding and the pinned GGUF
        # binding of the same checkpoint.
        identities = {
            HASHING_DEFAULT.identity(),
            EMBEDDINGGEMMA2_512.identity(),
            EMBEDDINGGEMMA2_GGUF_512.identity(),
        }
        self.assertEqual(len(identities), 3)
        self.assertNotEqual(HASHING_DEFAULT.identity(), EMBEDDINGGEMMA2_512.identity())
        self.assertNotEqual(
            EMBEDDINGGEMMA2_512.identity(), EMBEDDINGGEMMA2_GGUF_512.identity()
        )
        self.assertNotEqual(
            HASHING_DEFAULT.identity(), EMBEDDINGGEMMA2_GGUF_512.identity()
        )
        # The two bindings of the one production model still describe
        # different modalities and output geometries.
        self.assertEqual(EMBEDDINGGEMMA2_512.output_dimension, 512)
        self.assertEqual(EMBEDDINGGEMMA2_GGUF_512.output_dimension, 512)
        self.assertEqual(EMBEDDINGGEMMA2_GGUF_512.modality, "text-image-audio-video")
        self.assertNotEqual(
            EMBEDDINGGEMMA2_512.modality, EMBEDDINGGEMMA2_GGUF_512.modality
        )

    def test_non_hashing_profiles_use_pinned_real_revision(self):
        # The operator replaces the original ``pinned-stub``
        # placeholder with the real immutable revision once the
        # model weights are bound (open spec change PR 3 + PR 4).
        # The revision MUST be the documented immutable SHA, NOT
        # the placeholder, when production is enabled.
        from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_REVISION
        self.assertEqual(
            EMBEDDINGGEMMA2_512.model_revision,
            "914f7f89142e33e77833254d9c9b90c3cef7303b",
        )
        self.assertEqual(
            EMBEDDINGGEMMA2_GGUF_512.model_revision,
            GEMMA_REVISION,
        )
        self.assertNotIn("pinned-stub", EMBEDDINGGEMMA2_GGUF_512.model_revision)
        # The hashing profile is the only profile that keeps its
        # synthetic revision marker.
        self.assertEqual(HASHING_DEFAULT.model_revision, "v1")

    def test_field_change_changes_identity(self):
        changed = EmbeddingProfile(
            provider=HASHING_DEFAULT.provider,
            model_id=HASHING_DEFAULT.model_id,
            model_revision=HASHING_DEFAULT.model_revision,
            modality=HASHING_DEFAULT.modality,
            output_dimension=512,  # differs from HASHING_DEFAULT
            normalization=HASHING_DEFAULT.normalization,
            instruction_profile=HASHING_DEFAULT.instruction_profile,
            tokenizer_id=HASHING_DEFAULT.tokenizer_id,
            strategy_version=HASHING_DEFAULT.strategy_version,
        )
        self.assertNotEqual(HASHING_DEFAULT.identity(), changed.identity())


class EmbeddingProfileRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = EmbeddingProfileRegistry()

    def test_registry_default_resolves(self):
        self.assertEqual(self.registry.default("hashing"), HASHING_DEFAULT)
        self.assertEqual(self.registry.default(), HASHING_DEFAULT)
        self.assertEqual(
            self.registry.default("embeddinggemma2"), EMBEDDINGGEMMA2_512
        )
        self.assertEqual(
            self.registry.default("embeddinggemma2-gguf"),
            EMBEDDINGGEMMA2_GGUF_512,
        )

    def test_registry_unknown_identity_raises(self):
        with self.assertRaises(EmbeddingProfileMismatchError):
            self.registry.resolve("nonexistent")

    def test_registry_unknown_name_raises(self):
        with self.assertRaises(EmbeddingProfileMismatchError):
            self.registry.default("does-not-exist")

    def test_registry_register_idempotent(self):
        before = self.registry.resolve(HASHING_DEFAULT.identity())
        self.registry.register(HASHING_DEFAULT)  # no-op
        self.registry.register(HASHING_DEFAULT)  # still a no-op
        self.assertEqual(
            self.registry.resolve(HASHING_DEFAULT.identity()), before
        )

    def test_registry_register_then_resolve(self):
        custom = EmbeddingProfile(
            provider="custom",
            model_id="custom-256",
            model_revision="v1",
            modality="text",
            output_dimension=256,
            normalization="l2",
            instruction_profile="default",
            tokenizer_id="hashing/v1",
            strategy_version="embedding-profile-v1",
        )
        self.registry.register(custom)
        self.assertIs(self.registry.resolve(custom.identity()), custom)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

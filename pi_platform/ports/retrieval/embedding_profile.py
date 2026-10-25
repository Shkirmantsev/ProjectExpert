"""Embedding profile descriptor and identity registry (Change Package C1/C2).

Covers the ``embedding-execution-profile`` spec delta: every vector the
platform ever embeds is namespaced by an :class:`EmbeddingProfile`
identity key ``sha256(canonical(EmbeddingProfile))``. The canonical
serialisation is sorted-key JSON with no separators and no volatile
data (no timestamps, hostnames, paths), so two equivalent profiles in
different construction order always produce byte-identical identity
keys. Incompatible profiles therefore can never share a dense-index
namespace.

The registry resolves well-known profile names and identity hashes;
unknown identities raise :class:`EmbeddingProfileMismatchError` so a
vector / index mismatch fails loudly instead of silently mixing
vector spaces.

Production-hardening (open spec change
``production-semantic-search-and-branch-reconciliation``, PR 1):
the production profile now carries the immutable upstream
Hugging Face revision SHA-1 (plan §11) rather than the
``pinned-stub`` placeholder. The real revision was retrieved from
``https://huggingface.co/api/models/<id>`` during the change that
binds the production adapter; the same revision MUST be recorded
in :file:`distribution/licenses/model-licenses.json` so the
production-capability-gate can verify it.

Model consolidation (open spec change
``consolidate-embeddinggemma2-and-autoconfigure-inference``):
ProjectExpert offers exactly one production embedding model.
The retired Qwen3 profile, its registry entry and its alias are
gone. The pinned GGUF binding of EmbeddingGemma 2 (``Q8_0``
backbone plus ``Q8_0`` multimodal projector) is the production
default because it is the only binding that runs on Windows and
Linux with CUDA, Vulkan, an integrated GPU or CPU only.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from typing import Mapping


__all__ = [
    "EmbeddingProfile",
    "EmbeddingProfileRegistry",
    "EmbeddingProfileMismatchError",
    "HASHING_DEFAULT",
    "EMBEDDINGGEMMA2_512",
    "EMBEDDINGGEMMA2_GGUF_512",
    "MULTIMODAL_FIGURE_512",
    "GemmaRevisionDefault",
]


EMBEDDING_PROFILE_STRATEGY_VERSION = "embedding-profile-v1"


# Plan §11 / plan §101. The Hugging Face SHAs were retrieved from
# https://huggingface.co/api/models/<id> on 2026-10-19. Operators MAY
# override them through the documented environment variables so a
# private mirror or a downstream revision can be pinned without
# editing this file. The :file:`distribution/licenses/model-licenses.json`
# inventory records the same revision; a mismatch between the two
# sources fails the production-capability-gate.
GemmaRevisionDefault = "914f7f89142e33e77833254d9c9b90c3cef7303b"


class EmbeddingProfileMismatchError(RuntimeError):
    """Raised when a vector / index is incompatible with the active profile."""


@dataclass(frozen=True)
class EmbeddingProfile:
    """Immutable descriptor of one embedding vector space.

    The nine fields jointly identify a vector space. Changing any of
    them changes :meth:`identity`, so persisted vectors from a
    different profile can never be opened together.
    """

    provider: str
    model_id: str
    model_revision: str
    modality: str
    output_dimension: int
    normalization: str
    instruction_profile: str
    tokenizer_id: str
    strategy_version: str

    def canonical_bytes(self) -> bytes:
        """Byte-stable canonical JSON encoding (sorted keys, no whitespace)."""

        payload: Mapping[str, object] = asdict(self)
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")

    def identity(self) -> str:
        """Return sha256 hex of canonical(EmbeddingProfile)."""

        return hashlib.sha256(self.canonical_bytes()).hexdigest()


# Well-known built-in profiles. HASHING_DEFAULT stays the minimal-
# profile default so the platform boots with zero optional
# dependencies. The production profile carries the immutable
# Hugging Face revision SHA-1 of the upstream ``google/embeddinggemma-2``
# checkpoint (plan §11, §101) for the native Transformers binding, and a
# separate profile identity for the pinned GGUF binding that the portable
# deployment uses. The two bindings MUST NOT share a vector namespace.
# Override the revision through the ``PI_EMBEDDINGGEMMA2_REVISION``
# environment variable only for private mirrors; the override is recorded
# in :file:`distribution/licenses/model-licenses.json` for the
# production-capability-gate.
HASHING_DEFAULT = EmbeddingProfile(
    provider="hashing",
    model_id="hashing-1.0.0",
    model_revision="v1",
    modality="text",
    output_dimension=384,
    normalization="l2",
    instruction_profile="default",
    tokenizer_id="hashing/v1",
    strategy_version=EMBEDDING_PROFILE_STRATEGY_VERSION,
)

_EMBEDDINGGEMMA2_REVISION = os.environ.get(
    "PI_EMBEDDINGGEMMA2_REVISION", GemmaRevisionDefault,
)
EMBEDDINGGEMMA2_512 = EmbeddingProfile(
    provider="embeddinggemma2",
    model_id="google/embeddinggemma-2",
    model_revision=_EMBEDDINGGEMMA2_REVISION,
    modality="text-image",
    output_dimension=512,
    normalization="l2",
    instruction_profile="project-expert-gemma-search-v2",
    tokenizer_id=(
        f"google/embeddinggemma-2@{_EMBEDDINGGEMMA2_REVISION}"
    ),
    strategy_version="embedding-profile-v2-gemma-vision",
)


def _gemma_gguf_profile() -> EmbeddingProfile:
    """Build the pinned GGUF binding profile.

    Imported lazily from the adapter package so the ports layer keeps no
    dependency on the retrieval adapters. The identity deliberately embeds
    the artefact repository, revision, both checksums, the quantisation, the
    pooling type and the output geometry: a swapped backbone, a swapped
    projector or a changed quantisation produces a different identity and
    therefore a different ANN namespace.
    """

    from pi_platform.adapters.retrieval.gguf_artifacts import (
        GEMMA_FULL_DIMENSION,
        GEMMA_INDEX_DIMENSION,
        GEMMA_INSTRUCTION_PROFILE,
        GEMMA_MODEL_ID,
        GEMMA_POOLING,
        GEMMA_PROJECTOR_SHA256,
        GEMMA_QUANTIZATION,
        GEMMA_REVISION,
        GEMMA_SHA256,
        RUNTIME_VERSION,
    )

    return EmbeddingProfile(
        provider="llama.cpp-embeddinggemma2",
        model_id=GEMMA_MODEL_ID,
        model_revision=GEMMA_REVISION,
        modality="text-image-audio-video",
        output_dimension=GEMMA_INDEX_DIMENSION,
        normalization="l2",
        instruction_profile=GEMMA_INSTRUCTION_PROFILE,
        tokenizer_id=f"{GEMMA_MODEL_ID}@{GEMMA_REVISION}",
        strategy_version=(
            f"llama.cpp-{RUNTIME_VERSION}-{GEMMA_QUANTIZATION}-{GEMMA_POOLING}"
            f"-full{GEMMA_FULL_DIMENSION}-mrl{GEMMA_INDEX_DIMENSION}"
            f"-{GEMMA_SHA256}-{GEMMA_PROJECTOR_SHA256}"
        ),
    )


EMBEDDINGGEMMA2_GGUF_512 = _gemma_gguf_profile()

# The multimodal figure profile is intentionally still on the
# ``pinned-stub`` placeholder: the real multimodal binding is
# excluded from the production-capability-gate per
# :file:`openspec/changes/production-semantic-search-and-branch-reconciliation/excluded-profiles.md`.
# The placeholder is documented in
# :file:`distribution/licenses/model-licenses.json` so operators
# understand the gate boundary.
MULTIMODAL_FIGURE_512 = EmbeddingProfile(
    provider="multimodal-figure",
    model_id="multimodal-figure-512",
    model_revision="pinned-stub",
    modality="multimodal",
    output_dimension=512,
    normalization="l2",
    instruction_profile="figure-caption",
    tokenizer_id="embeddinggemma2/v1-stub",
    strategy_version=EMBEDDING_PROFILE_STRATEGY_VERSION,
)

_WELL_KNOWN: Mapping[str, EmbeddingProfile] = {
    "hashing": HASHING_DEFAULT,
    "embeddinggemma2": EMBEDDINGGEMMA2_512,
    "embeddinggemma2-gguf": EMBEDDINGGEMMA2_GGUF_512,
    "multimodal": MULTIMODAL_FIGURE_512,
}


class EmbeddingProfileRegistry:
    """Identity-keyed registry of known embedding profiles.

    The three built-in profiles are pre-registered on construction.
    :meth:`register` is idempotent: re-registering a profile whose
    identity is already known is a no-op.
    """

    def __init__(self) -> None:
        self._by_identity: dict[str, EmbeddingProfile] = {}
        for profile in _WELL_KNOWN.values():
            self.register(profile)

    def register(self, profile: EmbeddingProfile) -> None:
        """Register ``profile``; same identity is a no-op."""

        identity = profile.identity()
        if identity in self._by_identity:
            return
        self._by_identity[identity] = profile

    def resolve(self, identity: str) -> EmbeddingProfile:
        """Return the profile registered under ``identity``.

        Raises :class:`EmbeddingProfileMismatchError` when the
        identity is unknown.
        """

        try:
            return self._by_identity[identity]
        except KeyError:
            raise EmbeddingProfileMismatchError(
                f"embedding profile identity {identity!r} is not registered"
            ) from None

    def default(self, name: str = "hashing") -> EmbeddingProfile:
        """Return the built-in profile for a well-known name.

        Recognised names are ``hashing``, ``embeddinggemma2`` and
        ``embeddinggemma2-gguf``.
        """

        try:
            return _WELL_KNOWN[name]
        except KeyError:
            raise EmbeddingProfileMismatchError(
                f"unknown embedding profile name {name!r}"
            ) from None

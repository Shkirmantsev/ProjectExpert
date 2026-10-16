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
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Mapping


__all__ = [
    "EmbeddingProfile",
    "EmbeddingProfileRegistry",
    "EmbeddingProfileMismatchError",
    "HASHING_DEFAULT",
    "EMBEDDINGGEMMA2_512",
    "QWEN3_EMBEDDING_0_6B_1024",
    "MULTIMODAL_FIGURE_512",
]


EMBEDDING_PROFILE_STRATEGY_VERSION = "embedding-profile-v1"


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
# dependencies. The two production profiles carry a
# ``model_revision="pinned-stub"`` placeholder that the operator
# replaces with a real pinned revision when the model weights are
# bound in the follow-up C.1.5 adapter work.
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

EMBEDDINGGEMMA2_512 = EmbeddingProfile(
    provider="embeddinggemma2",
    model_id="embeddinggemma2-512",
    model_revision="pinned-stub",
    modality="text",
    output_dimension=512,
    normalization="l2",
    instruction_profile="matryoshka-512",
    tokenizer_id="embeddinggemma2/v1-stub",
    strategy_version=EMBEDDING_PROFILE_STRATEGY_VERSION,
)

QWEN3_EMBEDDING_0_6B_1024 = EmbeddingProfile(
    provider="qwen3-embedding-0.6b",
    model_id="qwen3-embedding-0.6b",
    model_revision="pinned-stub",
    modality="text",
    output_dimension=1024,
    normalization="l2",
    instruction_profile="query-document",
    tokenizer_id="qwen3-embedding/v1-stub",
    strategy_version=EMBEDDING_PROFILE_STRATEGY_VERSION,
)

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
    "qwen3-embedding-0.6b": QWEN3_EMBEDDING_0_6B_1024,
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
        ``qwen3-embedding-0.6b``.
        """

        try:
            return _WELL_KNOWN[name]
        except KeyError:
            raise EmbeddingProfileMismatchError(
                f"unknown embedding profile name {name!r}"
            ) from None

"""Embedding model factory (open spec change PR 1, plan §12).

Resolves a configured model alias (``gemma``, ``qwen``, the legacy
``embeddinggemma2`` / ``qwen3-embedding-0.6b`` aliases, ``hashing``)
into a real :class:`EmbeddingModelPort`. The factory honours:

* alias normalisation (plan §12 canonical aliases ``gemma`` /
  ``qwen``);
* the production-capability-gate boundary: production aliases MUST
  resolve to a real binding or the factory MUST raise
  :class:`EmbeddingModelError` with an actionable message naming the
  install command (plan §2.1, §15, §73);
* the explicit ``minimal`` startup profile which permits the
  hashing backend (plan §2.1, §63);
* the device selection (``cpu``, ``cuda``, ``mps``, ``auto``) from
  plan §13.

The factory is the single entry point that the CLI
``models pull``, the HTTP control plane ``PUT /api/v1/admin/retrieval``
and the :func:`build_production_retrieval_runtime` composition call.
"""

from __future__ import annotations

from typing import Mapping

from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
)
from pi_platform.ports.retrieval.embedding_profile import (
    EMBEDDINGGEMMA2_512,
    HASHING_DEFAULT,
    QWEN3_EMBEDDING_0_6B_1024,
    EmbeddingProfile,
)


__all__ = [
    "EmbeddingModelFactory",
    "EmbeddingAlias",
    "StartupProfile",
    "UnknownEmbeddingAliasError",
    "HASHING_ALIAS",
    "GEMMA_ALIAS",
    "QWEN_ALIAS",
    "PRODUCTION_ALIASES",
    "MINIMAL_ALIASES",
]


HASHING_ALIAS = "hashing"
GEMMA_ALIAS = "gemma"
QWEN_ALIAS = "qwen"
GGUF_ALIAS = "qwen-gguf"
GEMMA_GGUF_ALIAS = "gemma-gguf"

PRODUCTION_ALIASES = frozenset({GEMMA_ALIAS, QWEN_ALIAS, GGUF_ALIAS, GEMMA_GGUF_ALIAS})
MINIMAL_ALIASES = frozenset({HASHING_ALIAS})

_ALIAS_TO_LEGACY_NAME: Mapping[str, str] = {
    GEMMA_ALIAS: "embeddinggemma2",
    "embeddinggemma2": "embeddinggemma2",
    QWEN_ALIAS: "qwen3-embedding-0.6b",
    "qwen3-embedding-0.6b": "qwen3-embedding-0.6b",
    "qwen3": "qwen3-embedding-0.6b",
    HASHING_ALIAS: "hashing",
}


class UnknownEmbeddingAliasError(EmbeddingModelError):
    """Raised when the requested alias is not recognised by the factory."""


class StartupProfile:
    """The three public startup profiles (plan §63).

    ``PRODUCTION`` is the default and is selected when no explicit
    profile is configured. ``MINIMAL`` is the explicit diagnostic
    profile (hashing + flat) and MUST be selected explicitly.
    ``DEVELOPMENT`` is reserved for developer-mode extras and is
    not surfaced in the production user wizard.
    """

    PRODUCTION = "production"
    MINIMAL = "minimal"
    DEVELOPMENT = "development"

    @classmethod
    def all(cls) -> tuple[str, ...]:
        return (cls.PRODUCTION, cls.MINIMAL, cls.DEVELOPMENT)


class EmbeddingModelFactory:
    """Resolve an alias to a real :class:`EmbeddingModelPort`.

    Construction is cheap and side-effect free. The first call to
    :meth:`build` that resolves to a real adapter triggers the
    lazy model load.
    """

    def __init__(self, *, startup_profile: str = StartupProfile.PRODUCTION) -> None:
        if startup_profile not in StartupProfile.all():
            raise ValueError(
                f"unknown startup profile {startup_profile!r}; "
                f"expected one of {StartupProfile.all()}"
            )
        self._startup_profile = startup_profile

    @property
    def startup_profile(self) -> str:
        return self._startup_profile

    def resolve_profile(self, alias: str) -> EmbeddingProfile:
        """Return the :class:`EmbeddingProfile` for ``alias``.

        Raises :class:`UnknownEmbeddingAliasError` for unknown
        aliases. Does not instantiate the adapter; callers that
        only need the profile (e.g. the production-capability-gate)
        can use this method without paying the model load cost.
        """

        normalised = self._normalise_alias(alias)
        if normalised == HASHING_ALIAS:
            return HASHING_DEFAULT
        if normalised == GEMMA_ALIAS:
            return EMBEDDINGGEMMA2_512
        if normalised == GEMMA_GGUF_ALIAS:
            from .llama_cpp_embedding_model import GEMMA_GGUF_PROFILE
            return GEMMA_GGUF_PROFILE
        if normalised == GGUF_ALIAS:
            from .llama_cpp_embedding_model import GGUF_PROFILE
            return GGUF_PROFILE
        if normalised == QWEN_ALIAS:
            return QWEN3_EMBEDDING_0_6B_1024
        raise UnknownEmbeddingAliasError(
            f"unknown embedding alias {alias!r}; expected one of "
            f"{sorted(PRODUCTION_ALIASES | MINIMAL_ALIASES)}"
        )

    def build(
        self, alias: str, *, device: str = "auto", cache_folder: str | None = None,
    ) -> EmbeddingModelPort:
        """Build the adapter for ``alias``.

        In the ``production`` startup profile, real bindings are
        preferred and a missing real binding raises
        :class:`EmbeddingModelError` with the install command. In
        the ``minimal`` profile the hashing backend is permitted.
        The factory itself never silently substitutes one alias
        for another.
        """

        normalised = self._normalise_alias(alias)
        resolved_device = device

        if normalised == HASHING_ALIAS:
            if self._startup_profile != StartupProfile.MINIMAL:
                raise EmbeddingModelError("hashing requires the explicit minimal startup profile")
            # The
            # ``minimal`` profile is the only one that selects it
            # by default. The factory builds a fresh adapter so
            # callers can mutate stats without aliasing.
            from pi_platform.core.retrieval.embedding_model import (
                HashingEmbeddingModel,
            )
            return HashingEmbeddingModel()

        if normalised in {GGUF_ALIAS, GEMMA_GGUF_ALIAS}:
            from .llama_cpp_embedding_model import LlamaCppEmbeddingModel
            return LlamaCppEmbeddingModel(device=device, model_alias=normalised)

        if device == 'vulkan':
            raise EmbeddingModelError('Vulkan requires model gemma-gguf or qwen-gguf and the accelerator setup')

        if normalised == GEMMA_ALIAS:
            from pi_platform.adapters.retrieval.embeddinggemma2_embedding_model import (
                EmbeddingGemma2EmbeddingModel,
            )
            adapter = EmbeddingGemma2EmbeddingModel(
                profile=EMBEDDINGGEMMA2_512, device=resolved_device, cache_folder=cache_folder,
            )
            return adapter

        if normalised == QWEN_ALIAS:
            from pi_platform.adapters.retrieval.qwen3_embedding_model import (
                Qwen3EmbeddingModel,
            )
            adapter = Qwen3EmbeddingModel(
                profile=QWEN3_EMBEDDING_0_6B_1024, device=resolved_device, cache_folder=cache_folder,
            )
            return adapter

        raise UnknownEmbeddingAliasError(
            f"unknown embedding alias {alias!r}; expected one of "
            f"{sorted(PRODUCTION_ALIASES | MINIMAL_ALIASES)}"
        )

    @staticmethod
    def _normalise_alias(alias: str) -> str:
        if not alias:
            raise UnknownEmbeddingAliasError("embedding alias is empty")
        lowered = alias.strip().lower()
        if lowered in {HASHING_ALIAS, GEMMA_ALIAS, QWEN_ALIAS, GGUF_ALIAS, GEMMA_GGUF_ALIAS}:
            return lowered
        if lowered in _ALIAS_TO_LEGACY_NAME:
            # Legacy aliases map back to the canonical one.
            legacy = _ALIAS_TO_LEGACY_NAME[lowered]
            if legacy == "embeddinggemma2":
                return GEMMA_ALIAS
            if legacy == "qwen3-embedding-0.6b":
                return QWEN_ALIAS
            return legacy
        raise UnknownEmbeddingAliasError(
            f"unknown embedding alias {alias!r}; expected one of "
            f"{sorted(PRODUCTION_ALIASES | MINIMAL_ALIASES)}"
        )

    @staticmethod
    def _resolve_device(device: str) -> str:
        from pi_platform.adapters.config.runtime_device import select_device
        return select_device(device).device

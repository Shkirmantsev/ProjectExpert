"""Embedding model factory.

ProjectExpert ships exactly one production embedding model: EmbeddingGemma 2
in the pinned ``Q8_0`` quantisation, with the matching ``Q8_0`` multimodal
projector. The factory resolves a configured alias into a real
:class:`EmbeddingModelPort` and honours:

* alias normalisation, including the retired aliases, which are rejected
  with an actionable message instead of being silently substituted;
* the production-capability-gate boundary: production aliases MUST resolve
  to a real binding or the factory MUST raise
  :class:`EmbeddingModelError` with an actionable message naming the install
  command;
* the explicit ``minimal`` startup profile which permits the hashing
  backend;
* the device selection (``cpu``, ``cuda``, ``vulkan``, ``auto``).

The factory is the single entry point that the CLI ``models pull``, the HTTP
control plane ``PUT /api/v1/admin/retrieval`` and the
:func:`build_production_retrieval_runtime` composition call.
"""

from __future__ import annotations

from typing import Mapping

from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
)
from pi_platform.ports.retrieval.embedding_profile import (
    EMBEDDINGGEMMA2_512,
    EMBEDDINGGEMMA2_GGUF_512,
    HASHING_DEFAULT,
    EmbeddingProfile,
)


__all__ = [
    "EmbeddingModelFactory",
    "EmbeddingAlias",
    "StartupProfile",
    "UnknownEmbeddingAliasError",
    "RetiredEmbeddingAliasError",
    "HASHING_ALIAS",
    "GEMMA_ALIAS",
    "GEMMA_TORCH_ALIAS",
    "PRODUCTION_ALIASES",
    "MINIMAL_ALIASES",
    "RETIRED_ALIASES",
]


HASHING_ALIAS = "hashing"
#: Production default: the pinned GGUF binding of EmbeddingGemma 2.
GEMMA_ALIAS = "gemma"
#: Explicit opt-in: the native Transformers binding of the same checkpoint.
GEMMA_TORCH_ALIAS = "gemma-torch"

PRODUCTION_ALIASES = frozenset({GEMMA_ALIAS, GEMMA_TORCH_ALIAS})
MINIMAL_ALIASES = frozenset({HASHING_ALIAS})

#: The retired alternative embedding model. These aliases are rejected with
#: an actionable message; they are never silently mapped onto another model,
#: because the retired model has a different vector space.
RETIRED_ALIASES = frozenset(
    {"qwen", "qwen-gguf", "qwen3", "qwen3-embedding-0.6b"}
)

#: Aliases that resolve to the production default.
_ALIAS_TO_LEGACY_NAME: Mapping[str, str] = {
    GEMMA_ALIAS: GEMMA_ALIAS,
    "embeddinggemma2": GEMMA_ALIAS,
    "gemma-gguf": GEMMA_ALIAS,
    "ggml-org/embeddinggemma-2-gguf": GEMMA_ALIAS,
    GEMMA_TORCH_ALIAS: GEMMA_TORCH_ALIAS,
    "embeddinggemma2-torch": GEMMA_TORCH_ALIAS,
    "google/embeddinggemma-2": GEMMA_TORCH_ALIAS,
    HASHING_ALIAS: HASHING_ALIAS,
}


class UnknownEmbeddingAliasError(EmbeddingModelError):
    """Raised when the requested alias is not recognised by the factory."""


class RetiredEmbeddingAliasError(EmbeddingModelError):
    """Raised when a retired model alias is requested.

    The message names the supported alias so an operator with a stale
    configuration can repair it without reading the release notes.
    """


class StartupProfile:
    """The three public startup profiles.

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

        Raises :class:`UnknownEmbeddingAliasError` for unknown aliases and
        :class:`RetiredEmbeddingAliasError` for the retired alternative
        model. Does not instantiate the adapter; callers that only need the
        profile (e.g. the production-capability-gate) can use this method
        without paying the model load cost.
        """

        normalised = self._normalise_alias(alias)
        if normalised == HASHING_ALIAS:
            return HASHING_DEFAULT
        if normalised == GEMMA_ALIAS:
            return EMBEDDINGGEMMA2_GGUF_512
        if normalised == GEMMA_TORCH_ALIAS:
            return EMBEDDINGGEMMA2_512
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
        The factory itself never silently substitutes one alias for
        another.
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

        if normalised == GEMMA_ALIAS:
            # The pinned GGUF binding. It is the only binding that runs
            # on Windows and Linux with CUDA, Vulkan, an integrated GPU or
            # CPU only, and it is the only binding that exposes the full
            # multimodal package.
            from .llama_cpp_embedding_model import LlamaCppEmbeddingModel
            return LlamaCppEmbeddingModel(device=device)

        if normalised == GEMMA_TORCH_ALIAS:
            if device == "vulkan":
                raise EmbeddingModelError(
                    "the native binding supports cpu, cuda and mps only; "
                    "use the default 'gemma' binding for Vulkan or CUDA"
                )
            from pi_platform.adapters.retrieval.embeddinggemma2_embedding_model import (
                EmbeddingGemma2EmbeddingModel,
            )
            adapter = EmbeddingGemma2EmbeddingModel(
                profile=EMBEDDINGGEMMA2_512, device=resolved_device, cache_folder=cache_folder,
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
        if lowered in RETIRED_ALIASES:
            raise RetiredEmbeddingAliasError(
                f"the embedding model alias {alias!r} is retired; "
                f"ProjectExpert ships one production embedding model. "
                f"Select '{GEMMA_ALIAS}' for the pinned GGUF binding or "
                f"'{GEMMA_TORCH_ALIAS}' for the native binding."
            )
        if lowered in _ALIAS_TO_LEGACY_NAME:
            return _ALIAS_TO_LEGACY_NAME[lowered]
        raise UnknownEmbeddingAliasError(
            f"unknown embedding alias {alias!r}; expected one of "
            f"{sorted(PRODUCTION_ALIASES | MINIMAL_ALIASES)}"
        )

    @staticmethod
    def _resolve_device(device: str) -> str:
        from pi_platform.adapters.config.runtime_device import select_device
        return select_device(device).device

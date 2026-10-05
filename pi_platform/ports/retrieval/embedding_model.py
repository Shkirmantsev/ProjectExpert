"""Embedding model port for the v0.8 Phase 4 retrieval layer.

Covers architecture section §25 (Embedding Model) and the §5.4
model-license inventory contract. The :class:`EmbeddingModelPort`
exposes a multilingual, CPU-capable, replaceable embedding backend
to the Phase 4 retrieval pipeline and the Phase 3
:class:`pi_platform.ports.runtime.dense_index.DenseIndexPort`.

The default Phase 4 implementation lives in
:mod:`pi_platform.adapters.retrieval.hashing_embedding_model`
(stdlib-only) and
:mod:`pi_platform.adapters.retrieval.multilingual_st_embedding_model`
(multilingual sentence-transformers when the optional dependency
is installed).
"""

from __future__ import annotations

import abc
from typing import Mapping, Sequence


__all__ = [
    "EmbeddingModelPort",
    "EmbeddingModelError",
]


class EmbeddingModelError(RuntimeError):
    """Raised when an embedding model cannot satisfy a request."""


class EmbeddingModelPort(abc.ABC):
    """Abstract embedding model port.

    Implementations MUST be deterministic for a fixed
    :meth:`model_version` and a fixed input text (element-wise equal
    within the adapter-declared numerical tolerance).
    """

    @abc.abstractmethod
    def embed(self, text: str) -> Sequence[float]: ...

    @abc.abstractmethod
    def embed_batch(
        self, texts: Sequence[str],
    ) -> Sequence[Sequence[float]]: ...

    @abc.abstractmethod
    def dimension(self) -> int: ...

    @abc.abstractmethod
    def model_version(self) -> str: ...

    @abc.abstractmethod
    def license_id(self) -> str: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...
"""Host accelerator port and value types (G1)."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import List, Mapping, Sequence


__all__ = [
    "HostAcceleratorPort",
    "AcceleratorError",
    "HealthStatus",
    "AcceleratorCapabilities",
    "EmbeddingModelNotAllowed",
    "EmbeddingRequest",
    "EmbeddingResponse",
]


class AcceleratorError(RuntimeError):
    """Raised when the host accelerator cannot satisfy a request."""


class EmbeddingModelNotAllowed(AcceleratorError):
    """Raised when the requested model is not in the allow-list."""


@dataclass(frozen=True)
class HealthStatus:
    """Result of ``GET /health``."""

    status: str
    version: str
    uptime_seconds: float


@dataclass(frozen=True)
class AcceleratorCapabilities:
    """Result of ``GET /v1/capabilities``."""

    device: str
    free_memory_bytes: int
    model_ids: tuple[str, ...] = ()
    profile_identities: tuple[str, ...] = ()


@dataclass(frozen=True)
class EmbeddingRequest:
    """Body of ``POST /v1/embeddings``."""

    model_id: str
    input: str


@dataclass(frozen=True)
class EmbeddingResponse:
    """Response of ``POST /v1/embeddings``."""

    model_id: str
    embedding: tuple[float, ...]
    embedding_profile_hash: str


class HostAcceleratorPort(abc.ABC):
    """Abstract port for the host-side embedding accelerator."""

    @abc.abstractmethod
    def health(self) -> HealthStatus: ...

    @abc.abstractmethod
    def capabilities(self) -> AcceleratorCapabilities: ...

    @abc.abstractmethod
    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...

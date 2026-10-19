"""Embedding model port for the v0.8 Phase 4 retrieval layer.

Covers architecture section §25 (Embedding Model) and the §5.4
model-license inventory contract. The :class:`EmbeddingModelPort`
exposes a multilingual, CPU-capable, replaceable embedding backend
to the Phase 4 retrieval pipeline and the Phase 3
:class:`pi_platform.ports.runtime.dense_index.DenseIndexPort`.

Production-hardening (open spec change
``production-semantic-search-and-branch-reconciliation``, PR 2):
the port is extended with a role-aware
:class:`EmbeddingRequest` contract. Every embedding call MUST carry
an explicit role (query / document) and MAY carry a retrieval task
(defaults to :attr:`EmbeddingTask.SEARCH`) and an optional title.
The :meth:`embed` and :meth:`embed_batch` text-only entry points
remain as thin convenience wrappers for legacy callers but every
production caller MUST go through :meth:`embed_request` or
:meth:`embed_requests` so prompt-policy choices stay inside the
adapter and the prompt can never be silently elided.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence


__all__ = [
    "EmbeddingModelPort",
    "EmbeddingModelError",
    "EmbeddingRole",
    "EmbeddingTask",
    "EmbeddingRequest",
    "MissingEmbeddingRoleError",
]


class EmbeddingModelError(RuntimeError):
    """Raised when an embedding model cannot satisfy a request."""


class MissingEmbeddingRoleError(EmbeddingModelError):
    """Raised when an embedding call is made without an explicit role.

    The production contract (plan §7) forbids the port from
    assuming a default role. A request without role MUST be rejected
    so prompt misuse is detectable at the boundary instead of being
    silently flattened by the adapter.
    """


class EmbeddingRole(str, Enum):
    """Distinguishes a query embedding from a stored-document embedding.

    Plan §7 makes this distinction non-optional: the production
    sentence-transformers models benefit from asymmetric retrieval
    formatting and every call MUST declare its role explicitly.
    """

    QUERY = "query"
    DOCUMENT = "document"


class EmbeddingTask(str, Enum):
    """Task-specific prompt selector inside a model binding.

    Plan §7 enumerates three retrieval tasks: search (default),
    code retrieval and question answering. The exact prompt syntax
    is model-specific and is the adapter's responsibility; the port
    only carries the typed selector across the boundary.
    """

    SEARCH = "search"
    CODE_RETRIEVAL = "code-retrieval"
    QUESTION_ANSWERING = "question-answering"


@dataclass(frozen=True)
class EmbeddingRequest:
    """One embedding request with role, task, text and optional title.

    The title participates in document-side encoding (plan §9.4) for
    models that benefit from a title prefix. Query-side requests
    ignore the title. The text field is mandatory.
    """

    text: str
    role: EmbeddingRole
    task: EmbeddingTask = EmbeddingTask.SEARCH
    title: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.role, EmbeddingRole):
            # Defensive: dataclass type annotation is hint-only, so
            # surface a clear error if a caller passes a raw string.
            raise MissingEmbeddingRoleError(
                f"EmbeddingRequest.role must be an EmbeddingRole "
                f"instance, got {type(self.role).__name__}"
            )
        if not isinstance(self.task, EmbeddingTask):
            raise ValueError(
                f"EmbeddingRequest.task must be an EmbeddingTask "
                f"instance, got {type(self.task).__name__}"
            )


class EmbeddingModelPort(abc.ABC):
    """Abstract embedding model port.

    Implementations MUST be deterministic for a fixed
    :meth:`model_version` and a fixed input text (element-wise equal
    within the adapter-declared numerical tolerance).
    """

    @abc.abstractmethod
    def embed(self, text: str) -> Sequence[float]:
        """Convenience wrapper for the legacy text-only contract.

        Equivalent to
        ``self.embed_request(EmbeddingRequest(text, role=DOCUMENT))``.
        Production callers MUST prefer :meth:`embed_request`.
        """

    @abc.abstractmethod
    def embed_batch(
        self, texts: Sequence[str],
    ) -> Sequence[Sequence[float]]:
        """Convenience wrapper for the legacy text-only batch contract.

        Equivalent to
        ``self.embed_requests(EmbeddingRequest(t, DOCUMENT) for t in texts)``.
        Production callers MUST prefer :meth:`embed_requests`.
        """

    @abc.abstractmethod
    def embed_request(self, request: EmbeddingRequest) -> Sequence[float]:
        """Embed a single role-aware request."""

    @abc.abstractmethod
    def embed_requests(
        self, requests: Sequence[EmbeddingRequest],
    ) -> Sequence[Sequence[float]]:
        """Embed a batch of role-aware requests.

        Implementations SHOULD batch by role/task when the underlying
        runtime supports it (e.g. sentence-transformers ``prompts``).
        """

    @abc.abstractmethod
    def dimension(self) -> int: ...

    @abc.abstractmethod
    def model_version(self) -> str: ...

    @abc.abstractmethod
    def license_id(self) -> str: ...

    @abc.abstractmethod
    def profile(self): ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...

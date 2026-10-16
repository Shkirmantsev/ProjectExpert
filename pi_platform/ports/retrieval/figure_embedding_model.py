"""Figure embedding model port for the v0.8 multimodal profile.

Change Package H of the v0.8 refinement (``improve-ingestion-
retrieval-local-models``) adds an optional figure embedding
adapter behind the ``multimodal`` profile. The port follows
the same shape as :class:`EmbeddingModelPort` (text input
+ vector output) but carries a multimodal-modality
descriptor and a deterministic visual-content hash so a
real ``CLIP`` / ``OpenCLIP`` binding can be added later as
a follow-up change without breaking the contract.

The default implementation is a STUB that ships an
``EmbeddingModelError`` on every call so a Tier-1 / Tier-2
run never silently produces figure vectors; the real binding
ships in a follow-up change that adds the corresponding
optional dependency group to ``pyproject.toml`` and
``distribution/licenses/model-licenses.json``.

The port is also intentionally narrow: it only needs to
carry the ``modality`` and the ``dimension`` so the
:class:`EmbeddingProfile` registry (Package C2) can reject
incompatible vector spaces. A real adapter also exposes
``image_dimension`` and ``text_dimension`` so a CLIP-style
binding can run with the canonical shared embedding space.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass
from typing import Mapping, Sequence


__all__ = [
    "FigureEmbeddingModelPort",
    "FigureEmbeddingModelError",
    "Modality",
    "FigureEmbeddingRequest",
]


class Modality(str, enum.Enum):
    """The modality supported by an embedding or figure-embedding model."""

    TEXT = "text"
    CODE = "code"
    FIGURE = "figure"
    MULTIMODAL = "multimodal"


@dataclass(frozen=True)
class FigureEmbeddingRequest:
    """One multimodal embedding request.

    ``text_hint`` is an optional caption / heading that the
    STUB concatenates with the figure content-hash so the
    deterministic fallback emits a stable vector. The real
    binding would use the caption as the textual view of the
    figure when computing cross-modal similarity.
    """

    figure_id: str
    content_hash: str
    text_hint: str = ""


class FigureEmbeddingModelError(RuntimeError):
    """Raised when the multimodal adapter cannot satisfy a request."""


class FigureEmbeddingModelPort(abc.ABC):
    """Abstract figure embedding port.

    Implementations MUST be deterministic for a fixed
    :meth:`model_version` and a fixed
    :class:`FigureEmbeddingRequest`. The textual input is
    ``text_hint`` when present, falling back to the figure
    content hash; the real CLIP binding would consume the
    figure's pixel data.
    """

    @abc.abstractmethod
    def embed_figure(
        self, request: FigureEmbeddingRequest,
    ) -> Sequence[float]: ...

    @abc.abstractmethod
    def dimension(self) -> int: ...

    @abc.abstractmethod
    def model_version(self) -> str: ...

    @abc.abstractmethod
    def license_id(self) -> str: ...

    @abc.abstractmethod
    def is_available(self) -> bool: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...

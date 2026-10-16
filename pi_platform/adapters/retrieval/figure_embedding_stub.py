"""Figure embedding model STUB adapter (Change Package H).

Change Package H of the v0.8 refinement ships the optional
multimodal figure-embedding adapter behind the
``multimodal`` profile. The STUB follows the same pattern
as the EmbeddingGemma2 / Qwen3 STUB adapters from Package C:
the contract is real, the implementation raises a
:class:`FigureEmbeddingModelError` on every call so a
Tier-1 / Tier-2 run never silently produces figure vectors.

The real binding ships in a follow-up change that adds
the corresponding optional dependency group to
``pyproject.toml`` and ``distribution/licenses/model-
licenses.json``. The STUB is a no-op adapter: it advertises
the documented ``multimodal.figures`` feature flag, returns
``is_available() = False`` and reports zero stats so the
Control Plane diagnostics panel can show the missing
binding to the operator.

The STUB also exposes :meth:`is_available` so the
:func:`pi_platform.core.control.diagnostics.v0_8_panels`
status panel (Package I1) can render the multimodal field
as ``disabled`` when no real binding is installed.
"""

from __future__ import annotations

import hashlib
from typing import Mapping, Sequence

from pi_platform.ports.retrieval.figure_embedding_model import (
    FigureEmbeddingModelError,
    FigureEmbeddingModelPort,
    FigureEmbeddingRequest,
)


__all__ = ["FigureEmbeddingModelStub"]


#: Stable identifier for the multimodal profile. The
#: :class:`EmbeddingProfile` registry (Package C2) keys
#: figure-vector namespaces on this identity.
MULTIMODAL_PROFILE_IDENTITY = "multimodal/figure-stub/v1"

#: Output dimension. The real CLIP-style binding would
#: expose a 512 / 768 / 1024-dimensional vector; the STUB
#: uses a small fixed dimension so the deterministic hash
#: output stays in the byte range.
STUB_DIMENSION = 64


class FigureEmbeddingModelStub(FigureEmbeddingModelPort):
    """STUB figure embedding adapter.

    The STUB is wired behind the ``multimodal`` profile and
    raises :class:`FigureEmbeddingModelError` on every embed
    call so a Tier-1 / Tier-2 run never accidentally produces
    figure vectors. The ``is_available()`` predicate returns
    ``False`` so the Control Plane diagnostics panel can
    surface the missing binding to the operator; the real
    binding ships in a follow-up change.
    """

    def __init__(self, *, available: bool = False) -> None:
        self._available = bool(available)
        self._calls = 0
        self._errors = 0

    def embed_figure(
        self, request: FigureEmbeddingRequest,
    ) -> Sequence[float]:
        self._calls += 1
        if not self._available:
            self._errors += 1
            raise FigureEmbeddingModelError(
                "FigureEmbeddingModelStub is a no-op STUB; the "
                "real multimodal binding ships in a follow-up "
                "change. Enable it through the "
                "'multimodal.figures' feature flag after the "
                "real CLIP / OpenCLIP binding is installed."
            )
        # When the binding is enabled the STUB returns a
        # deterministic hash-based vector so the rest of
        # the pipeline can be smoke-tested end-to-end. The
        # hash covers the request's content hash + text
        # hint so a repeated request returns the same
        # vector.
        digest = hashlib.sha256()
        digest.update(request.figure_id.encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(request.content_hash.encode("utf-8"))
        digest.update(b"\x1f")
        digest.update((request.text_hint or "").encode("utf-8"))
        seed = digest.digest()
        # Repeat the seed across the vector so the dimension
        # is stable; the values are 8-bit unsigned integers
        # scaled to [0, 1) so the deterministic fallback
        # is unit-norm-ish.
        return [
            ((seed[i % len(seed)] / 255.0) - 0.5) * 0.1
            for i in range(STUB_DIMENSION)
        ]

    def dimension(self) -> int:
        return STUB_DIMENSION

    def model_version(self) -> str:
        return MULTIMODAL_PROFILE_IDENTITY

    def license_id(self) -> str:
        # The STUB is platform-owned; the real binding's
        # license will be recorded in
        # distribution/licenses/model-licenses.json when the
        # follow-up change adds the real adapter.
        return "Apache-2.0"

    def is_available(self) -> bool:
        return self._available

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "errors": self._errors,
            "available": int(self._available),
            "dimension": STUB_DIMENSION,
        }

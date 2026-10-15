"""Asset (figure / image) adapter (E6).

Owns the binary asset lifecycle: image bytes go to the local
content-addressed store (CAS) under
``.project-intelligence-cache/assets/``. The adapter preserves
the plan §21.6 contract: figures are first-class
:class:`AssetRef` records with page, bbox, caption, OCR text,
and graph relations.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.document_graph import (
    AssetRef,
    ElementKind,
)
from pi_platform.ports.runtime.document_graph_store import (
    DocumentGraphStoreError,
    DocumentGraphStorePort,
)


__all__ = [
    "FigureAssetAdapter",
    "FigureAssetError",
]


class FigureAssetError(RuntimeError):
    """Raised when a figure asset cannot be persisted or read."""


class FigureAssetAdapter:
    """Adapter for binary figure assets.

    Image bytes go to the local CAS
    (``.project-intelligence-cache/assets/<byte_hash>``) by
    default; the adapter records an :class:`AssetRef` in the
    :class:`DocumentGraphStorePort` so the retrieval pipeline can
    join the figure to the chunk that mentions it.
    """

    def __init__(
        self,
        graph_store: DocumentGraphStorePort,
        *,
        cas_root: str = ".project-intelligence-cache",
    ) -> None:
        self._graph_store = graph_store
        self._cas_root = cas_root

    def store_figure(
        self,
        *,
        asset_id: str,
        image_bytes: bytes,
        mime_type: str,
        page: int,
        bbox: Sequence[float] = (),
    ) -> AssetRef:
        byte_hash = hashlib.sha256(image_bytes).hexdigest()
        cas_path = self._write_to_cas(byte_hash, image_bytes)
        asset = AssetRef(
            asset_id=asset_id or byte_hash,
            byte_hash=byte_hash,
            mime_type=mime_type,
            cas_path=cas_path,
            page=page,
            bbox=tuple(float(x) for x in bbox),
        )
        self._graph_store.put_asset(asset)
        return asset

    def attach_figure_to_element(
        self, asset: AssetRef, *, element_id: str, revision_id: str,
    ) -> None:
        # A real implementation would also write a Relation row;
        # for the v0.8 refinement stub the asset is recorded in
        # the graph store, and the chunk anchor's asset_id is
        # populated by the Docling adapter.
        return None

    def _write_to_cas(self, byte_hash: str, image_bytes: bytes) -> str:
        path = os.path.join(self._cas_root, "assets", byte_hash)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Idempotent: only write if the file is absent (CAS is
        # content-addressed; if the bytes are present the file
        # already exists).
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(image_bytes)
        return path

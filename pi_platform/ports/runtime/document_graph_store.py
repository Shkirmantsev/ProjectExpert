"""Document graph store port (E4).

Logical extension of the existing :mod:`pi_platform.ports.runtime.runtime_store`
module: the rich document graph (revisions, pages, elements, assets,
tables, chunk anchors) lives in a separate port with its own
SQLite adapter, but shares the same physical ``runtime.db`` with
the existing canonical ``runtime_entries`` table.
"""

from __future__ import annotations

import abc
from typing import Mapping, Optional, Sequence, Tuple

from pi_platform.core.canonical.document_graph import (
    AssetRef,
    DocumentElement,
    DocumentRevision,
    Page,
    SourceAnchor,
    TableGrid,
)


__all__ = [
    "DocumentGraphStorePort",
    "DocumentGraphStoreError",
]


class DocumentGraphStoreError(RuntimeError):
    """Raised when the document graph store cannot satisfy a request."""


class DocumentGraphStorePort(abc.ABC):
    """Abstract port for the rich document graph store."""

    @abc.abstractmethod
    def put_revision(self, rev: DocumentRevision) -> None: ...

    @abc.abstractmethod
    def get_revision(self, revision_id: str) -> Optional[DocumentRevision]: ...

    @abc.abstractmethod
    def list_revisions(self, source_id: str) -> Tuple[DocumentRevision, ...]: ...

    @abc.abstractmethod
    def put_page(self, revision_id: str, page: Page) -> None: ...

    @abc.abstractmethod
    def list_pages(self, revision_id: str) -> Tuple[Page, ...]: ...

    @abc.abstractmethod
    def put_element(
        self, revision_id: str, element: DocumentElement,
    ) -> None: ...

    @abc.abstractmethod
    def list_elements(
        self, revision_id: str, page: Optional[int] = None,
    ) -> Tuple[DocumentElement, ...]: ...

    @abc.abstractmethod
    def put_asset(self, asset: AssetRef) -> None: ...

    @abc.abstractmethod
    def get_asset(self, asset_id: str) -> Optional[AssetRef]: ...

    @abc.abstractmethod
    def put_table(
        self, revision_id: str, element_id: str, table: TableGrid,
    ) -> None: ...

    @abc.abstractmethod
    def get_table(
        self, revision_id: str, element_id: str,
    ) -> Optional[TableGrid]: ...

    @abc.abstractmethod
    def put_chunk_anchor(
        self, chunk_id: str, anchor: SourceAnchor,
    ) -> None: ...

    @abc.abstractmethod
    def list_chunk_anchors(
        self, chunk_id: str,
    ) -> Tuple[SourceAnchor, ...]: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...

"""PDF conversion and neutral document mapping; production errors fail closed."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

from pi_platform.core.canonical.document_graph import (
    AssetRef,
    DocumentElement,
    DocumentRevision,
    ElementKind,
    IngestionCheckpoint,
    IngestionState,
    Page,
    TableGrid,
    SourceAnchor,
)
from pi_platform.core.canonical.value_types import (
    Document,
    Entity,
    Evidence,
    KnowledgeState,
    Metadata,
    Relation,
    Section,
)
from pi_platform.ports.ingest.ingestion_job_store import IngestionJobStorePort
from pi_platform.ports.ingest.ocr_engine import (
    OcrEnginePort,
    SelectiveOcrPolicy,
)
from pi_platform.ports.ingest.prescan import PrescanPort
from pi_platform.ports.ingest.source_adapter import (
    Source,
    SourceAdapterContext,
    SourceContentFamily,
    SourceAdapterError,
    SourceAdapterPort,
    SourceParseResult,
)
from pi_platform.adapters.pdf.real_docling import (
    RealDoclingConverter,
    is_docling_available,
)
from pi_platform.ports.runtime.document_graph_store import DocumentGraphStorePort


__all__ = [
    "DoclingPdfAdapter",
    "DoclingPdfAdapterError",
    "DoclingMapper",
    "DEFAULT_DOCLING_STRATEGY_VERSION",
    "DEFAULT_PAGE_BATCH_SIZE",
    "DEFAULT_BOUNDARY_CONTEXT_PAGES",
    "build_real_docling_pdf_adapter",
]


DEFAULT_DOCLING_STRATEGY_VERSION = "docling-pdf/v2-real"
DEFAULT_PAGE_BATCH_SIZE = 32
DEFAULT_BOUNDARY_CONTEXT_PAGES = 1


class DoclingPdfAdapterError(SourceAdapterError):
    """Raised when the Docling PDF adapter cannot parse a source."""


def build_real_docling_pdf_adapter(
    prescan: PrescanPort,
    job_store: IngestionJobStorePort,
    graph_store: DocumentGraphStorePort,
    *,
    ocr_engine: Optional[OcrEnginePort] = None,
    strategy_version: str = DEFAULT_DOCLING_STRATEGY_VERSION,
    page_batch_size: int = DEFAULT_PAGE_BATCH_SIZE,
    boundary_context_pages: int = DEFAULT_BOUNDARY_CONTEXT_PAGES,
    embedding_model_id: str = "google/embeddinggemma-2",
    max_tokens: int = 512,
    asset_root: str = "tmp/local/pdf-assets",
    docling_converter: Optional["RealDoclingConverter"] = None,
) -> DoclingPdfAdapter:
    """Production factory for the Docling PDF adapter.

    This is the production entry point documented by open spec
    change PR 10 (plan §45, §46, §71): the adapter returned by
    this function MUST be wired to the real
    ``docling.document_converter.DocumentConverter``; the
    synthesised stub path is reserved for unit tests that do not
    load the real models.

    The factory refuses to build a "production" adapter when
    :func:`is_docling_available` returns ``False`` unless the
    caller supplies a pre-built ``docling_converter``. The
    production-capability-gate reads :func:`is_docling_available`
    to fail closed when Docling is absent; this factory is the
    matching enforcement point for the adapter layer.
    """

    if docling_converter is None:
        if not is_docling_available():
            raise DoclingPdfAdapterError(
                "docling is not installed; "
                "build_real_docling_pdf_adapter requires the real "
                "docling package (open spec change PR 10, plan §45)"
            )
        docling_converter = RealDoclingConverter(
            embedding_model_id=embedding_model_id,
            max_tokens=max_tokens,
        )
    return DoclingPdfAdapter(
        prescan=prescan,
        job_store=job_store,
        graph_store=graph_store,
        ocr_engine=ocr_engine,
        strategy_version=strategy_version,
        page_batch_size=page_batch_size,
        boundary_context_pages=boundary_context_pages,
        docling_converter=docling_converter,
        asset_root=asset_root,
    )


# ---------------------------------------------------------------------------
# Synthesised Docling types (kept private to this module).
# Private projection DTOs shared by vendor mapping and explicit test fixtures.
# No vendor objects cross the source adapter boundary.
# ---------------------------------------------------------------------------


@dataclass
class _DoclingTextItem:
    text: str
    page: int = 1
    bbox: Tuple[float, ...] = ()
    kind: ElementKind = ElementKind.PARAGRAPH


@dataclass
class _DoclingTableItem:
    headers: Tuple[str, ...]
    rows: Tuple[Tuple[str, ...], ...]
    page: int = 1
    bbox: Tuple[float, ...] = ()


@dataclass
class _DoclingFigureItem:
    caption: str
    page: int = 1
    bbox: Tuple[float, ...] = ()
    asset_bytes: bytes = b""


@dataclass
class _DoclingDocument:
    """Synthesised Docling document.

    The real ``docling.document_converter.DocumentConverter``
    returns a ``DoclingDocument``; this stub mimics the
    relevant fields so the mapper can run end-to-end.
    """

    page_count: int = 1
    text_items: Tuple[_DoclingTextItem, ...] = ()
    tables: Tuple[_DoclingTableItem, ...] = ()
    figures: Tuple[_DoclingFigureItem, ...] = ()
    author: str = ""
    producer: str = ""
    creation_date: str = ""
    language: str = "und"


# ---------------------------------------------------------------------------
# Docling → ProjectExpert neutral mapper
# ---------------------------------------------------------------------------


class DoclingMapper:
    """Map private projection DTOs into neutral canonical types.

    The mapper is the only place where Docling-side structure is
    decoded; the rest of the platform sees only the neutral
    types from :mod:`pi_platform.core.canonical.document_graph`.
    """

    def project_revision(
        self,
        *,
        doc: _DoclingDocument,
        source_id: str,
        byte_hash: str,
        strategy_version: str,
        ingested_at: str,
    ) -> DocumentRevision:
        return DocumentRevision(
            revision_id=byte_hash,
            source_id=source_id,
            byte_hash=byte_hash,
            strategy_version=strategy_version,
            ingested_at=ingested_at,
            page_count=doc.page_count,
            language=doc.language or "und",
            author=doc.author,
        )

    def project_pages(self, doc: _DoclingDocument) -> List[Page]:
        return [
            Page(
                page_no=p, native_text_present=True, ocr_used=False,
                language_hint=doc.language or "und",
            )
            for p in range(1, doc.page_count + 1)
        ]

    def project_elements(
        self, doc: _DoclingDocument, revision_id: str,
    ) -> List[DocumentElement]:
        out: List[DocumentElement] = []
        for i, t in enumerate(doc.text_items):
            element_id = self._element_id(
                revision_id, t.page, t.kind, t.bbox, t.text,
                ordinal=sum(x.page == t.page for x in doc.text_items[:i]),
            )
            out.append(DocumentElement(
                element_id=element_id, kind=t.kind,
                page=t.page, bbox=t.bbox, text=t.text,
                content_hash=hashlib.sha256(t.text.encode("utf-8")).hexdigest(),
                semantic_key=f"text/{t.page}/{i}",
            ))
        for i, tbl in enumerate(doc.tables):
            element_id = self._element_id(
                revision_id, tbl.page, ElementKind.TABLE, tbl.bbox,
                "|".join(tbl.headers), ordinal=sum(x.page == tbl.page for x in doc.tables[:i]),
            )
            serialised = self._serialise_table(tbl)
            out.append(DocumentElement(
                element_id=element_id, kind=ElementKind.TABLE,
                page=tbl.page, bbox=tbl.bbox, text=serialised,
                content_hash=hashlib.sha256(
                    serialised.encode("utf-8")
                ).hexdigest(),
                semantic_key=f"table/{tbl.page}/{i}",
            ))
        for i, fig in enumerate(doc.figures):
            element_id = self._element_id(
                revision_id, fig.page, ElementKind.FIGURE, fig.bbox,
                fig.caption, ordinal=sum(x.page == fig.page for x in doc.figures[:i]),
            )
            out.append(DocumentElement(
                element_id=element_id, kind=ElementKind.FIGURE,
                page=fig.page, bbox=fig.bbox, text=fig.caption,
                content_hash=hashlib.sha256(
                    fig.caption.encode("utf-8")
                ).hexdigest(),
                semantic_key=f"figure/{fig.page}/{i}",
            ))
        return out

    def project_tables(
        self, doc: _DoclingDocument, revision_id: str,
    ) -> List[Tuple[str, TableGrid]]:
        out: List[Tuple[str, TableGrid]] = []
        for i, tbl in enumerate(doc.tables):
            element_id = self._element_id(
                revision_id, tbl.page, ElementKind.TABLE, tbl.bbox,
                "|".join(tbl.headers), ordinal=sum(x.page == tbl.page for x in doc.tables[:i]),
            )
            out.append((element_id, TableGrid(
                headers=tbl.headers,
                rows=tbl.rows,
                serialised_markdown=self._serialise_table(tbl),
                repeat_header=True,
            )))
        return out

    def project_figures(
        self, doc: _DoclingDocument, revision_id: str,
    ) -> List[AssetRef]:
        out: List[AssetRef] = []
        for i, fig in enumerate(doc.figures):
            byte_hash = hashlib.sha256(fig.asset_bytes).hexdigest() \
                if fig.asset_bytes else hashlib.sha256(
                    fig.caption.encode("utf-8"),
                ).hexdigest()
            element_id = self._element_id(
                revision_id, fig.page, ElementKind.FIGURE, fig.bbox,
                fig.caption,
                ordinal=sum(x.page == fig.page for x in doc.figures[:i]),
            )
            out.append(AssetRef(
                asset_id=element_id,
                byte_hash=byte_hash,
                mime_type="image/png",
                cas_path=f".project-intelligence-cache/assets/{byte_hash}",
                page=fig.page, bbox=fig.bbox,
            ))
        return out

    # -- helpers -----------------------------------------------------

    @staticmethod
    def _serialise_table(tbl: _DoclingTableItem) -> str:
        lines = []
        if tbl.headers:
            lines.append("| " + " | ".join(tbl.headers) + " |")
            lines.append("|" + "|".join(["---"] * len(tbl.headers)) + "|")
        for r in tbl.rows:
            lines.append("| " + " | ".join(r) + " |")
        return "\n".join(lines)

    @staticmethod
    def _element_id(
        revision_id: str, page: int, kind: ElementKind,
        bbox: Sequence[float], content_seed: str, *,
        ordinal: int = 0,
    ) -> str:
        bbox_str = ",".join(f"{float(x):.2f}" for x in bbox) or "0"
        seed = f"{revision_id}|{page}|{kind.value}|{bbox_str}|{content_seed}|{ordinal}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# The Docling PDF adapter
# ---------------------------------------------------------------------------


class DoclingPdfAdapter(SourceAdapterPort):
    """Source adapter for the PDF family.

    Batches the parse into page windows of
    :data:`DEFAULT_PAGE_BATCH_SIZE` with
    :data:`DEFAULT_BOUNDARY_CONTEXT_PAGES` neighbour pages as
    context. Each batch commits to the
    :class:`DocumentGraphStorePort` and to the
    :class:`IngestionJobStorePort`. A crash at page 417 does not
    invalidate completed batches; the next call resumes at
    ``next_page`` and re-parses only the owned page window.
    """

    def __init__(
        self,
        prescan: PrescanPort,
        job_store: IngestionJobStorePort,
        graph_store: DocumentGraphStorePort,
        *,
        ocr_engine: Optional[OcrEnginePort] = None,
        strategy_version: str = DEFAULT_DOCLING_STRATEGY_VERSION,
        page_batch_size: int = DEFAULT_PAGE_BATCH_SIZE,
        boundary_context_pages: int = DEFAULT_BOUNDARY_CONTEXT_PAGES,
        docling_converter: Optional["RealDoclingConverter"] = None,
        allow_synthetic: bool = False,
        asset_root: str = "tmp/local/pdf-assets",
    ) -> None:
        if page_batch_size < 1 or boundary_context_pages < 0:
            raise ValueError("invalid PDF page batch configuration")
        self._allow_synthetic = allow_synthetic
        self._asset_root = asset_root
        self._prescan = prescan
        self._job_store = job_store
        self._graph_store = graph_store
        self._ocr_engine = ocr_engine
        self._ocr_policy = SelectiveOcrPolicy()
        self._strategy_version = strategy_version
        self._page_batch_size = page_batch_size
        self._boundary_context_pages = boundary_context_pages
        self._mapper = DoclingMapper()
        self._docling_converter = docling_converter
        if docling_converter is None and not allow_synthetic:
            self._docling_converter = RealDoclingConverter()

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.PDF

    def parse(
        self, source: Source, context: Optional[SourceAdapterContext] = None,
    ) -> SourceParseResult:
        if not source or not getattr(source, "uri", None):
            raise DoclingPdfAdapterError(
                "Source.uri is required for DoclingPdfAdapter"
            )
        prescan = self._prescan.scan(source.uri)
        native_pages = None
        if isinstance(self._docling_converter, RealDoclingConverter):
            try:
                native_pages = self._docling_converter.inspect_pdf(source.uri)
                prescan = replace(prescan, page_count=len(native_pages),
                                  has_native_text=all(native_pages))
            except Exception as exc:
                raise DoclingPdfAdapterError(f"PDF source {source.uri!r}: {exc}") from exc
        if prescan.file_size == 0:
            raise DoclingPdfAdapterError(
                f"source {source.uri!r} is empty after prescan"
            )
        cached_revision = self._graph_store.get_revision(prescan.byte_hash)
        if cached_revision is not None and cached_revision.strategy_version != self._strategy_version:
            raise DoclingPdfAdapterError(
                f"PDF source {source.uri!r} has an incompatible cached graph "
                f"({cached_revision.strategy_version}); rebuild the runtime PDF cache "
                "before parsing with the real converter")
        # Short-circuit when a previous run already finished
        # for the same (source_id, revision_id, strategy).
        existing = self._job_store.find_completed(
            source_id=source.id, revision_id=prescan.byte_hash,
            strategy_version=self._strategy_version,
        )
        if existing is not None:
            # Reconstruct the SourceParseResult from the graph
            # store; this is the cheap path.
            rev = self._graph_store.get_revision(prescan.byte_hash)
            if rev is not None:
                return self._rebuild_from_graph(source, rev)
        # Otherwise, run a fresh batched parse.
        return self._parse_in_batches(source, prescan, native_pages=native_pages)

    # -- internal helpers --------------------------------------------

    def _parse_in_batches(
        self, source: Source, prescan, *, native_pages=None,
    ) -> SourceParseResult:
        """Page-windowed parse with per-batch commits.

        Only owned pages are persisted; neighbouring context is discarded.
        Conversion failures preserve completed page windows for restart.
        """
        identity = f"{source.id}|{prescan.byte_hash}|{self._strategy_version}"
        job_id = "job-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        checkpoint = self._job_store.get(job_id)
        if checkpoint is None:
            checkpoint = IngestionCheckpoint(
                job_id=job_id, source_id=source.id,
                revision_id=prescan.byte_hash,
                strategy_version=self._strategy_version,
                state=IngestionState.PENDING,
            )
            self._job_store.create(checkpoint)
        self._job_store.mark_running(job_id)
        revision = None
        for first in range(checkpoint.next_page, prescan.page_count + 1, self._page_batch_size):
            last = min(first + self._page_batch_size - 1, prescan.page_count)
            window = (max(1, first - self._boundary_context_pages),
                      min(prescan.page_count, last + self._boundary_context_pages))
            try:
                if self._docling_converter is not None:
                    window_native = (all(native_pages[window[0] - 1:window[1]])
                                     if native_pages is not None else prescan.has_native_text)
                    doc = self._convert_real_or_synthesise(
                        source, replace(prescan, has_native_text=window_native), page_range=window)
                else:
                    doc = self._synthesise_doc(prescan)
                revision = self._mapper.project_revision(
                    doc=doc, source_id=source.id, byte_hash=prescan.byte_hash,
                    strategy_version=self._strategy_version, ingested_at=datetime.now(timezone.utc).isoformat(),
                )
                self._graph_store.put_revision(revision)
                for page_no in range(first, last + 1):
                    native = (native_pages[page_no - 1] if native_pages is not None
                              else prescan.has_native_text)
                    self._graph_store.put_page(prescan.byte_hash, Page(
                        page_no=page_no, native_text_present=native, ocr_used=not native))
                mapped_elements = self._mapper.project_elements(doc, prescan.byte_hash)
                elements_by_id = {element.element_id: element for element in mapped_elements}
                for element in mapped_elements:
                    if first <= element.page <= last:
                        self._graph_store.put_element(prescan.byte_hash, element)
                for element_id, table in self._mapper.project_tables(doc, prescan.byte_hash):
                    element = elements_by_id[element_id]
                    if first <= element.page <= last:
                        self._graph_store.put_table(prescan.byte_hash, element_id, table)
                from pi_platform.adapters.pdf.assets import FigureAssetAdapter
                assets = FigureAssetAdapter(self._graph_store, cas_root=self._asset_root)
                for fig, asset in zip(doc.figures, self._mapper.project_figures(doc, prescan.byte_hash)):
                    if first <= fig.page <= last and fig.asset_bytes:
                        assets.store_figure(asset_id=asset.asset_id, image_bytes=fig.asset_bytes,
                                            mime_type=asset.mime_type, page=fig.page, bbox=fig.bbox)
                    elif first <= fig.page <= last and self._allow_synthetic:
                        self._graph_store.put_asset(asset)
                self._job_store.mark_batch_done(job_id, (first, last))
            except Exception as exc:
                error = f"PDF source {source.uri!r}, pages {first}-{last}: {exc}"
                self._job_store.mark_failed(job_id, (first, last), error)
                raise DoclingPdfAdapterError(error) from exc
        self._job_store.mark_completed(job_id)
        revision = self._graph_store.get_revision(prescan.byte_hash)
        return self._rebuild_from_graph(source, revision)

    def _rebuild_from_graph(
        self, source: Source, revision: DocumentRevision,
    ) -> SourceParseResult:
        """Reconstruct a SourceParseResult from the persisted
        rich document graph (cheap path after a completed run)."""
        return self._build_source_parse_result(source, revision)

    def _build_source_parse_result(
        self, source: Source, revision: DocumentRevision,
    ) -> SourceParseResult:
        # Project into the generic Document / Section / Chunk
        # representation. This is a thin projection over the
        # rich document graph.
        from pi_platform.core.ingest.records import make_chunk
        source_path = getattr(source.metadata, "sourcePath", None)
        source_metadata = source.metadata
        if isinstance(source.metadata, Mapping):
            source_path = source.metadata.get("sourcePath", source_path)
            source_metadata = Metadata(
                documentId=source.id, version=revision.strategy_version,
                language=revision.language or "und",
            )
            source_metadata = replace(source_metadata, **{
                k: v for k, v in source.metadata.items() if k in Metadata.__dataclass_fields__
            })
        document = Document(
            id=revision.revision_id, title=getattr(source, "name", None) or revision.source_id,
            metadata=replace(source_metadata, documentId=revision.revision_id,
                             version=revision.strategy_version, language=revision.language or "und",
                             sourcePath=source_path or source.uri, contentHash=source.contentHash),
        )
        sections = []
        for element in self._graph_store.list_elements(revision.revision_id):
            section = Section(id=f"sec-{element.element_id}", heading=f"Page {element.page}", level=1)
            attrs = {"sourceFamily": "pdf", "page": element.page, "elementKind": element.kind.value}
            table = self._graph_store.get_table(revision.revision_id, element.element_id)
            if table is not None:
                attrs["table"] = {"headers": table.headers, "rows": table.rows}
            chunk = make_chunk(document, section, element.text,
                               parser_version=self._strategy_version, extensions=attrs)
            asset = (self._graph_store.get_asset(element.element_id)
                     if element.kind == ElementKind.FIGURE else None)
            chunk = replace(chunk, metadata=replace(chunk.metadata, page=element.page),
                            anchors=(SourceAnchor(
                revision_id=revision.revision_id, page=element.page,
                element_id=element.element_id, bbox=element.bbox,
                asset_id=asset.asset_id if asset else ""),))
            sections.append(replace(section, chunks=(chunk,)))
        document = replace(document, sections=tuple(sections))
        return SourceParseResult(
            document=document,
            sections=tuple(sections),
            knowledge_state=KnowledgeState.VERIFIED,
            parser_version=self._strategy_version,
            rationale=(
                f"docling pdf adapter; {revision.page_count} pages; "
                f"author={revision.author!r}; language={revision.language!r}"
            ),
        )

    @staticmethod
    def _provenance(item):
        prov = getattr(item, "prov", ()) or ()
        if not prov:
            raise DoclingPdfAdapterError("Docling structural item has no page provenance")
        bbox = getattr(prov[0], "bbox", None)
        coords = tuple(float(getattr(bbox, k)) for k in ("l", "t", "r", "b")) if bbox else ()
        return int(prov[0].page_no), coords

    def _convert_real_or_synthesise(self, source, prescan, *, page_range=None):
        """Map real output; conversion or mapping failures never synthesize content."""
        raw = self._docling_converter.convert(
            source.uri, page_range=page_range, do_ocr=not prescan.has_native_text)
        texts = []
        for item in getattr(raw, "texts", ()):
            page, bbox = self._provenance(item)
            text = str(getattr(item, "text", "") or "")
            if text:
                label = getattr(getattr(item, "label", None), "value", "text")
                kind = {"title": ElementKind.HEADING, "section_header": ElementKind.HEADING,
                        "list_item": ElementKind.LIST, "formula": ElementKind.FORMULA}.get(
                            label, ElementKind.PARAGRAPH)
                texts.append(_DoclingTextItem(text=text, page=page, bbox=bbox, kind=kind))
        tables = []
        for item in getattr(raw, "tables", ()):
            page, bbox = self._provenance(item)
            data = item.data
            grid = [["" for _ in range(data.num_cols)] for _ in range(data.num_rows)]
            header_rows = set()
            for cell in data.table_cells:
                for row in range(cell.start_row_offset_idx, cell.end_row_offset_idx):
                    for col in range(cell.start_col_offset_idx, cell.end_col_offset_idx):
                        grid[row][col] = cell.text
                    if cell.column_header:
                        header_rows.add(row)
            headers = tuple(" / ".join(grid[r][c] for r in sorted(header_rows))
                            for c in range(data.num_cols)) if header_rows else ()
            rows = tuple(tuple(row) for i, row in enumerate(grid) if i not in header_rows)
            tables.append(_DoclingTableItem(headers=headers, rows=rows, page=page, bbox=bbox))
        figures = []
        for item in getattr(raw, "pictures", ()):
            page, bbox = self._provenance(item)
            caption = item.caption_text(raw) or f"Figure on page {page}"
            image = item.get_image(raw)
            image_bytes = b""
            if image is not None:
                import io
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                image_bytes = buf.getvalue()
            figures.append(_DoclingFigureItem(caption=caption, page=page, bbox=bbox,
                                              asset_bytes=image_bytes))
        return _DoclingDocument(page_count=prescan.page_count, text_items=tuple(texts),
                                tables=tuple(tables), figures=tuple(figures),
                                author=prescan.metadata.get("author", ""))

    def _synthesise_doc(self, prescan) -> _DoclingDocument:
        """Synthesise a DoclingDocument from the prescan.

        Used only when the caller explicitly enables synthetic fixture mode.
        """
        page_count = prescan.page_count
        # One paragraph per page; one table on page 1; one figure
        # on page 2.
        text_items = tuple(
            _DoclingTextItem(
                text=f"Page {p} content. " * 4,
                page=p, bbox=(0.0, 0.0, 612.0, 792.0),
            )
            for p in range(1, page_count + 1)
        )
        tables: Tuple[_DoclingTableItem, ...] = ()
        if page_count >= 1:
            tables = (
                _DoclingTableItem(
                    headers=("Col A", "Col B"),
                    rows=(("a1", "b1"), ("a2", "b2")),
                    page=1, bbox=(0.0, 700.0, 612.0, 792.0),
                ),
            )
        figures: Tuple[_DoclingFigureItem, ...] = ()
        if page_count >= 2:
            figures = (
                _DoclingFigureItem(
                    caption="Figure 1: synthesised figure",
                    page=2, bbox=(0.0, 0.0, 300.0, 200.0),
                    asset_bytes=b"",  # STUB; real binding provides bytes
                ),
            )
        return _DoclingDocument(
            page_count=page_count,
            text_items=text_items,
            tables=tables,
            figures=figures,
            author=prescan.metadata.get("author", ""),
            producer=prescan.metadata.get("producer", ""),
            creation_date=prescan.metadata.get("creation_date", ""),
            language="und",
        )

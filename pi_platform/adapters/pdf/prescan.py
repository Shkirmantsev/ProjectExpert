"""Stdlib-only PDF prescan adapter (E2).

This adapter does NOT import ``pypdf`` / ``pdfplumber`` /
``pypdf2`` — those are optional extras. The prescan is purely a
byte-level sniff: it counts ``%PDF-`` headers, looks for
``/Type /Page`` object declarations in a tail-window, samples
``BT...ET`` text-block markers, and extracts ``/Author`` /
``/Producer`` / ``/CreationDate`` from the trailer.

The real Docling-bound parser (E3) is a follow-up that
delegates to the optional dependency. This prescan is enough
to decide whether the heavy parser is worth invoking and
whether the page has a usable native text layer (which gates
the OCR policy in E5).
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Dict, Optional

from pi_platform.ports.ingest.prescan import (
    DEFAULT_PRESCAN_STRATEGY_VERSION,
    PrescanError,
    PrescanPort,
    PrescanResult,
)


__all__ = ["PdfPrescanAdapter", "PDF_HEADER_PREFIX", "PDF_HEADER_RE"]


PDF_HEADER_PREFIX = b"%PDF-"
PDF_HEADER_RE = re.compile(rb"%PDF-(\d+)\.(\d+)")
PAGE_OBJECT_RE = re.compile(rb"/Type\s*/Page(?![s/])")
TEXT_BLOCK_RE = re.compile(rb"BT\b.*?ET", re.DOTALL)
TRAILER_RE = re.compile(rb"trailer\b(.*?)(?=startxref|%%EOF)", re.DOTALL)
INFO_AUTHOR_RE = re.compile(rb"/Author\s*\(([^)]*)\)")
INFO_PRODUCER_RE = re.compile(rb"/Producer\s*\(([^)]*)\)")
INFO_CREATIONDATE_RE = re.compile(rb"/CreationDate\s*\(([^)]*)\)")


def _read_tail(path: str, size: int, tail: int) -> bytes:
    """Return the last `tail` bytes of the file (or the whole
    file if smaller)."""
    with open(path, "rb") as f:
        if size <= tail:
            f.seek(0)
            return f.read(size)
        f.seek(size - tail)
        return f.read(tail)


def _read_head(path: str, head: int) -> bytes:
    with open(path, "rb") as f:
        return f.read(head)


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _decode_pdf_string(raw: bytes) -> str:
    """Best-effort decode of a PDF string literal value.

    PDF strings are either parenthesised literals (which we
    scan) or hex strings (``<...>``). For the metadata fields
    we care about (Author, Producer, CreationDate) the
    parenthesised form is by far the most common. Decoding is
    permissive: Latin-1 round-trip with a few common
    replacements.
    """
    try:
        return raw.decode("latin-1").strip()
    except (UnicodeDecodeError, ValueError):
        return ""


class PdfPrescanAdapter(PrescanPort):
    """Byte-only PDF prescan (no third-party dependency)."""

    # Default sample sizes: enough to find the page-object count
    # and a few BT...ET blocks without reading a 600-page PDF
    # into memory.
    DEFAULT_HEAD = 1024 * 1024          # 1 MiB
    DEFAULT_TAIL = 64 * 1024            # 64 KiB
    DEFAULT_TEXT_SAMPLE = 200 * 1024    # 200 KiB

    def __init__(
        self,
        *,
        head: int = DEFAULT_HEAD,
        tail: int = DEFAULT_TAIL,
        text_sample: int = DEFAULT_TEXT_SAMPLE,
    ) -> None:
        self._head = head
        self._tail = tail
        self._text_sample = text_sample

    def scan(self, source_path: str) -> PrescanResult:
        if not os.path.isfile(source_path):
            raise PrescanError(f"file not found: {source_path!r}")
        size = os.path.getsize(source_path)
        if size == 0:
            raise PrescanError(f"file is empty: {source_path!r}")
        # Verify the PDF header.
        head_chunk = _read_head(source_path, min(self._head, 16))
        if not head_chunk.startswith(PDF_HEADER_PREFIX):
            raise PrescanError(
                f"file is not a PDF: header {head_chunk[:8]!r} does "
                f"not start with %PDF-"
            )
        # Read the rest of the head sample.
        if size > 16:
            head_chunk = _read_head(source_path, min(self._head, size))
        # Count the page objects in the tail window.
        tail_chunk = _read_tail(source_path, size, self._tail)
        page_count = len(PAGE_OBJECT_RE.findall(tail_chunk))
        # Sample the head for BT...ET blocks.
        text_sample_chunk = head_chunk[: self._text_sample]
        text_blocks = TEXT_BLOCK_RE.findall(text_sample_chunk)
        sample_text_chars = sum(len(b) for b in text_blocks)
        has_native_text = bool(text_blocks)
        # Trailer metadata.
        metadata: Dict[str, str] = {}
        trailer_match = TRAILER_RE.search(tail_chunk)
        if trailer_match is not None:
            trailer = trailer_match.group(1)
            for key, pattern, field in (
                ("author", INFO_AUTHOR_RE, "Author"),
                ("producer", INFO_PRODUCER_RE, "Producer"),
                ("creation_date", INFO_CREATIONDATE_RE, "CreationDate"),
            ):
                m = pattern.search(trailer)
                if m is not None:
                    metadata[key] = _decode_pdf_string(m.group(1))
        return PrescanResult(
            page_count=page_count or 1,   # 1 page minimum
            metadata=metadata,
            has_native_text=has_native_text,
            sample_text_chars=sample_text_chars,
            byte_hash=_hash_file(source_path),
            strategy_version=DEFAULT_PRESCAN_STRATEGY_VERSION,
            file_size=size,
        )

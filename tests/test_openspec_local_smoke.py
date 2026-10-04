"""Smoke tests for the Phase 2 default and OpenSpec source adapters."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pi_platform.adapters.fs.local_source_adapter import LocalSourceAdapter  # noqa: E402
from pi_platform.adapters.openspec.openspec_change_adapter import (  # noqa: E402
    OpenSpecChangeAdapter,
    OpenSpecChunker,
    OpenSpecEntityExtractor,
)
from pi_platform.core.canonical.content_address import (  # noqa: E402
    content_address_bytes,
)
from pi_platform.core.canonical.value_types import (  # noqa: E402
    Document,
    Metadata,
    Section,
    Source,
)


def _metadata() -> Metadata:
    return Metadata(documentId="doc-1", version="0.0.0", language="openspec")


def _synthetic_document() -> Document:
    return Document(
        id="doc-1",
        title="Example change",
        sections=(
            Section(id="s-purpose", heading="Purpose: Ingest documents", level=2),
            Section(id="s-req", heading="Requirement: SourceAdapter port", level=3),
        ),
        metadata=_metadata(),
    )


def _synthetic_source() -> Source:
    return Source(
        id="change-example",
        uri="openspec/changes/example-change/proposal.md",
        family="openspec",
        contentHash=content_address_bytes(b"synthetic"),
        metadata=_metadata(),
    )


class ConstructionTests(unittest.TestCase):
    def test_all_classes_construct(self) -> None:
        self.assertIsInstance(LocalSourceAdapter(), LocalSourceAdapter)
        self.assertIsInstance(OpenSpecChangeAdapter(), OpenSpecChangeAdapter)
        self.assertIsInstance(OpenSpecChunker(), OpenSpecChunker)
        self.assertIsInstance(OpenSpecEntityExtractor(), OpenSpecEntityExtractor)


class ExtractorSmokeTests(unittest.TestCase):
    def test_extract_returns_tuple_of_two_non_empty_sequences(self) -> None:
        result = OpenSpecEntityExtractor().extract(
            _synthetic_document(), _synthetic_source()
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        entities, relations = result
        self.assertGreater(len(entities), 0)
        self.assertGreater(len(relations), 0)


class ChunkerSmokeTests(unittest.TestCase):
    def test_chunk_returns_tuple(self) -> None:
        document = _synthetic_document()
        result = OpenSpecChunker().chunk(document, document.sections, None)
        self.assertIsInstance(result, tuple)


class LocalSourceParseSmokeTests(unittest.TestCase):
    def test_parse_plain_text_returns_document(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            Path(path).write_text("hello world\n", encoding="utf-8")
            source = Source(
                id="src-plain",
                uri=path,
                family="plain_text",
                contentHash=content_address_bytes(b"hello world\n"),
            )
            result = LocalSourceAdapter().parse(source, None)
            self.assertIsInstance(result.document, Document)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()

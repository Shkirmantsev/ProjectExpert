"""Retrieval text builder tests (Change Package B4).

Covers the context-enrichment delta: the canonical
``retrieval_text = context_prefix + "\\n\\n" + raw_text`` mapping,
semantic-field inclusion, forbidden-field exclusion with raise-on-leak,
hash stability, and the opt-in local contextualizer summary path.
"""

from __future__ import annotations

import dataclasses
import hashlib
import unittest
from types import SimpleNamespace

from pi_platform.core.canonical.value_types import Chunk, Document, Metadata, Section
from pi_platform.core.ingest.retrieval_text_builder import (
    DeterministicRetrievalTextBuilder,
    LocalContextualizerRetrievalTextBuilder,
)
from pi_platform.ports.ingest.retrieval_text_builder import (
    DEFAULT_STRATEGY_VERSION,
    RetrievalTextBuilderError,
)


COMMIT = "a" * 40
CONTENT_SHA = "b" * 64


def _metadata(**extensions) -> Metadata:
    base = {
        "timestamp": "2026-10-04T12:00:00",
        "bbox": [0, 0, 10, 10],
        "parserVersion": "structural-chunker-1",
    }
    base.update(extensions)
    return Metadata(
        documentId="doc-1",
        version="0.0.0",
        language="en",
        section="Packing",
        businessDomain="PACKING",
        module="erp",
        className="Packer",
        requirementId="REQ-123",
        sourcePath="/home/user/project/doc.md",
        gitCommit=COMMIT,
        contentHash=CONTENT_SHA,
        securityClassification="CONFIDENTIAL",
        extensions=base,
    )


def _chunk(metadata: Metadata | None = None) -> Chunk:
    return Chunk(
        "c1",
        "raw body",
        "raw body",
        metadata or _metadata(),
        "doc.md",
        "hash-c1",
        parentId="sec-1",
    )


def _document(title: str = "Packing Guide") -> Document:
    return Document("doc-1", title)


def _section(heading: str = "Overview") -> Section:
    return Section("sec-1", heading, 2)


class DeterministicBuilderTests(unittest.TestCase):
    def setUp(self):
        self.builder = DeterministicRetrievalTextBuilder()

    def _build(self, **kwargs):
        arguments = dict(
            chunk=_chunk(),
            document=_document(),
            section=_section(),
            metadata=_metadata(caption="order packing figure", protocol_name="FinishPack"),
        )
        arguments.update(kwargs)
        return self.builder.build(**arguments)

    def test_includes_semantic_fields(self):
        result = self._build()
        expected_prefix_lines = [
            "document_title: Packing Guide",
            "section: Overview",
            "businessDomain: PACKING",
            "module: erp",
            "className: Packer",
            "requirementId: REQ-123",
            "caption: order packing figure",
            "protocol_name: FinishPack",
        ]
        for line in expected_prefix_lines:
            self.assertIn(line, result.deterministic_parts)
        self.assertEqual(len(result.deterministic_parts), 8)

    def test_excludes_forbidden_fields(self):
        result = self._build()
        for forbidden in (
            "/home/user/project/doc.md",
            COMMIT,
            CONTENT_SHA,
            "CONFIDENTIAL",
            "2026-10-04",
            "structural-chunker-1",
            "bbox",
        ):
            self.assertNotIn(forbidden, result.text)
            self.assertNotIn(forbidden, "\n".join(result.deterministic_parts))

    def test_single_canonical_mapping(self):
        result = self._build()
        prefix = "\n".join(result.deterministic_parts)
        self.assertEqual(result.text, prefix + "\n\n" + "raw body")
        self.assertEqual(result.inferred_parts, ())
        self.assertEqual(result.strategy_version, DEFAULT_STRATEGY_VERSION)

    def test_content_hash_is_stable(self):
        first = self._build()
        second = self._build()
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(
            first.content_hash,
            hashlib.sha256(first.text.encode("utf-8")).hexdigest(),
        )
        changed = dataclasses.replace(_chunk(), rawText="different body")
        other = self._build(chunk=changed)
        self.assertNotEqual(first.content_hash, other.content_hash)

    def test_metadata_falls_back_to_chunk_metadata(self):
        result = self.builder.build(
            chunk=_chunk(), document=None, section=None, metadata=None
        )
        self.assertIn("section: Packing", result.deterministic_parts)
        self.assertNotIn("document_title", "\n".join(result.deterministic_parts))

    def test_forbidden_semantic_value_raises(self):
        with self.assertRaises(RetrievalTextBuilderError):
            self._build(document=_document(title="/home/user/secret.md"))
        with self.assertRaises(RetrievalTextBuilderError):
            self._build(document=_document(title=COMMIT))


class LocalContextualizerBuilderTests(unittest.TestCase):
    def setUp(self):
        self.builder = LocalContextualizerRetrievalTextBuilder()

    def _build(self, enrichment):
        return self.builder.build(
            chunk=_chunk(),
            document=_document(),
            section=_section(),
            metadata=_metadata(),
            local_enrichment=enrichment,
        )

    def test_local_summary_is_appended_as_inferred_part(self):
        enrichment = SimpleNamespace(context_summary="Packing runs near orders.")
        result = self._build(enrichment)
        self.assertEqual(
            result.inferred_parts, ("inferred: Packing runs near orders.",)
        )
        self.assertIn("inferred: Packing runs near orders.", result.text)
        self.assertTrue(result.text.endswith("raw body"))
        prefix = "\n".join(result.deterministic_parts + result.inferred_parts)
        self.assertEqual(result.text, prefix + "\n\n" + "raw body")

    def test_summary_attribute_is_accepted(self):
        enrichment = SimpleNamespace(summary="Glossary: pack = pick.")
        result = self._build(enrichment)
        self.assertEqual(len(result.inferred_parts), 1)
        self.assertIn("Glossary: pack = pick.", result.inferred_parts[0])

    def test_no_enrichment_delegates_to_deterministic_builder(self):
        result = self._build(None)
        self.assertEqual(result.inferred_parts, ())
        deterministic = DeterministicRetrievalTextBuilder().build(
            chunk=_chunk(),
            document=_document(),
            section=_section(),
            metadata=_metadata(),
        )
        self.assertEqual(result, deterministic)

    def test_authoritative_keyed_lines_are_dropped(self):
        enrichment = SimpleNamespace(
            context_summary=(
                "requirement_id: REQ-999\n"
                "protocol_version: 9.9\n"
                "packing context hint"
            )
        )
        result = self._build(enrichment)
        self.assertNotIn("REQ-999", result.text)
        self.assertNotIn("9.9", result.text)
        self.assertEqual(
            result.inferred_parts, ("inferred: packing context hint",)
        )


class DefaultBuilderIgnoresEnrichmentTests(unittest.TestCase):
    def test_default_ignores_local_enrichment(self):
        enrichment = SimpleNamespace(context_summary="Packing runs near orders.")
        deterministic = DeterministicRetrievalTextBuilder()
        with_enrichment = deterministic.build(
            chunk=_chunk(),
            document=_document(),
            section=_section(),
            metadata=_metadata(),
            local_enrichment=enrichment,
        )
        without_enrichment = deterministic.build(
            chunk=_chunk(),
            document=_document(),
            section=_section(),
            metadata=_metadata(),
        )
        self.assertEqual(with_enrichment, without_enrichment)


if __name__ == "__main__":
    unittest.main()

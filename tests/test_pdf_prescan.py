"""Tests for the PDF prescan adapter (E2)."""

from __future__ import annotations

import os
import tempfile
import unittest


from pi_platform.ports.ingest.prescan import (
    PrescanError,
    PrescanResult,
)
from pi_platform.adapters.pdf.prescan import PdfPrescanAdapter


def _write(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


class PdfPrescanSmokeTests(unittest.TestCase):
    """The prescan is byte-only; tests synthesize minimal PDFs
    that exercise the header / page-count / native-text / metadata
    detection."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="prescan-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(
            self._tmp, ignore_errors=True,
        ))

    def test_prescan_minimal_pdf(self) -> None:
        path = os.path.join(self._tmp, "minimal.pdf")
        _write(path, (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
            b"trailer\n<< /Info <</Author (Test Author) "
            b"/Producer (Test Producer) /CreationDate (20261015)>> /Size 4 "
            b"/Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
        ))
        result = PdfPrescanAdapter().scan(path)
        self.assertIsInstance(result, PrescanResult)
        self.assertEqual(result.page_count, 1)
        self.assertEqual(result.metadata.get("author"), "Test Author")
        self.assertEqual(result.metadata.get("producer"), "Test Producer")
        self.assertEqual(result.metadata.get("creation_date"), "20261015")
        self.assertFalse(result.has_native_text)
        # byte_hash is a 64-char hex.
        self.assertEqual(len(result.byte_hash), 64)
        self.assertEqual(result.strategy_version, "prescan/v1")
        self.assertGreater(result.file_size, 0)

    def test_prescan_detects_native_text(self) -> None:
        path = os.path.join(self._tmp, "with-text.pdf")
        _write(path, (
            b"%PDF-1.4\n"
            b"BT\n"
            b"/F1 12 Tf\n"
            b"100 700 Td\n"
            b"(Hello world from the prescan fixture) Tj\n"
            b"ET\n"
            b"trailer\n<< /Size 1 >>\n%%EOF\n"
        ))
        result = PdfPrescanAdapter().scan(path)
        self.assertTrue(result.has_native_text)
        self.assertGreater(result.sample_text_chars, 0)

    def test_prescan_counts_multiple_pages(self) -> None:
        path = os.path.join(self._tmp, "three-page.pdf")
        # Build a multi-page PDF with three /Type /Page objects
        # in the trailer block (the last 64 KiB of the file).
        # The prescan only counts page objects in its tail window.
        padding = b"x" * 50000
        body = b"%PDF-1.4\n" + padding
        for i in range(3):
            body += f"{i+3} 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n".encode()
        body += b"trailer\n<< /Size 1 >>\n%%EOF\n"
        _write(path, body)
        result = PdfPrescanAdapter().scan(path)
        self.assertEqual(result.page_count, 3)

    def test_prescan_rejects_non_pdf(self) -> None:
        path = os.path.join(self._tmp, "not-a-pdf.bin")
        _write(path, b"not a pdf\n")
        with self.assertRaises(PrescanError):
            PdfPrescanAdapter().scan(path)

    def test_prescan_rejects_missing_file(self) -> None:
        with self.assertRaises(PrescanError):
            PdfPrescanAdapter().scan(os.path.join(self._tmp, "missing.pdf"))

    def test_prescan_rejects_empty_file(self) -> None:
        path = os.path.join(self._tmp, "empty.pdf")
        _write(path, b"")
        with self.assertRaises(PrescanError):
            PdfPrescanAdapter().scan(path)

    def test_prescan_byte_hash_stable(self) -> None:
        path = os.path.join(self._tmp, "stable.pdf")
        _write(path, b"%PDF-1.4\n%%EOF\n")
        a = PdfPrescanAdapter().scan(path)
        b = PdfPrescanAdapter().scan(path)
        self.assertEqual(a.byte_hash, b.byte_hash)

    def test_prescan_byte_hash_changes_with_content(self) -> None:
        path1 = os.path.join(self._tmp, "a.pdf")
        path2 = os.path.join(self._tmp, "b.pdf")
        _write(path1, b"%PDF-1.4\n%%EOF\n")
        _write(path2, b"%PDF-1.5\n%%EOF\n")
        a = PdfPrescanAdapter().scan(path1)
        b = PdfPrescanAdapter().scan(path2)
        self.assertNotEqual(a.byte_hash, b.byte_hash)

    def test_prescan_strategy_version(self) -> None:
        path = os.path.join(self._tmp, "v.pdf")
        _write(path, b"%PDF-1.4\n%%EOF\n")
        result = PdfPrescanAdapter().scan(path)
        self.assertEqual(result.strategy_version, "prescan/v1")


class PrescanPortContractTests(unittest.TestCase):
    def test_prescan_port_is_abstract(self) -> None:
        from pi_platform.ports.ingest.prescan import PrescanPort
        import inspect
        self.assertTrue(inspect.isabstract(PrescanPort))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

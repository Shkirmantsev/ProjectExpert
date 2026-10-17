"""Tesseract OCR adapter (E5 default).

This is the production STUB: the adapter owns the contract and
the binding point for the real ``pytesseract`` import (the real
adapter ships in a follow-up change once ``pytesseract`` /
``tesserocr`` are added to the ``documents`` optional
dependency group). The stub preserves the
:class:`OcrEnginePort` surface so the policy layer can be wired
without a third-party dependency.
"""

from __future__ import annotations

from pi_platform.ports.ingest.ocr_engine import (
    OcrEngineError,
    OcrEnginePort,
    OcrResult,
    TESSERACT_LICENSE_ID,
)


__all__ = ["TesseractOcrAdapter", "TESSERACT_DEFAULT_REVISION"]


TESSERACT_DEFAULT_REVISION = "tesseract-5.x-stub"


class TesseractOcrAdapter(OcrEnginePort):
    """Tesseract OCR adapter (STUB).

    The real binding is a follow-up: the
    ``pi_platform.adapters.ingest.ocr.TesseractRealAdapter`` will
    import ``pytesseract`` and translate the image bytes to text
    via ``image_to_string``. Until then, ``ocr_page`` raises
    :class:`OcrEngineError` with a clear message.
    """

    @property
    def engine_name(self) -> str:
        return "tesseract"

    @property
    def engine_revision(self) -> str:
        return TESSERACT_DEFAULT_REVISION

    @property
    def license_id(self) -> str:
        return TESSERACT_LICENSE_ID

    def ocr_page(
        self, *, image_bytes: bytes, language_hint: str = "und",
    ) -> OcrResult:
        raise OcrEngineError(
            "Tesseract OCR is not bound in this build; install the "
            "'documents' optional dependency group to enable the "
            "real pytesseract binding."
        )

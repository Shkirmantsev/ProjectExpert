"""OCR engine port (E5).

Selective OCR policy (plan §21.4): only invoke an OCR engine on
image-only pages, never OCR native-text pages. OCR engines are
adapters behind this port; the default candidate is Tesseract,
the optional fallback is PaddleOCR. Both are subject to the
License Gate and pinned in
``distribution/licenses/model-licenses.json``.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence


__all__ = [
    "OcrEnginePort",
    "OcrEngineError",
    "OcrResult",
    "OcrPolicyDecision",
    "SelectiveOcrPolicy",
    "TESSERACT_LICENSE_ID",
    "PADDLEOCR_LICENSE_ID",
]


TESSERACT_LICENSE_ID = "Apache-2.0"
PADDLEOCR_LICENSE_ID = "Apache-2.0"


class OcrEngineError(RuntimeError):
    """Raised when an OCR engine cannot satisfy a request."""


@dataclass(frozen=True)
class OcrResult:
    """OCR output for a single page or image region."""

    text: str
    confidence: float = 0.0
    engine: str = ""
    engine_revision: str = ""
    license_id: str = ""


@dataclass(frozen=True)
class OcrPolicyDecision:
    """The decision of the selective OCR policy for one page."""

    page_no: int
    should_ocr: bool
    reason: str
    candidate_engine: str = "tesseract"


class OcrEnginePort(abc.ABC):
    """Adapter contract: turn an image into text."""

    @property
    @abc.abstractmethod
    def engine_name(self) -> str: ...

    @property
    @abc.abstractmethod
    def engine_revision(self) -> str: ...

    @property
    @abc.abstractmethod
    def license_id(self) -> str: ...

    @abc.abstractmethod
    def ocr_page(
        self, *, image_bytes: bytes, language_hint: str = "und",
    ) -> OcrResult: ...


class SelectiveOcrPolicy:
    """Apply the plan §21.4 policy: OCR only when needed.

    Rule: a page is OCR'd only when its native text layer is
    unusable. If ``native_text_present`` is True, the policy
    returns ``should_ocr=False`` with a clear reason. Otherwise
    the page is OCR'd with the candidate engine (Tesseract by
    default, PaddleOCR as an opt-in fallback).
    """

    def __init__(
        self,
        *,
        primary_engine: str = "tesseract",
        fallback_engine: str = "paddleocr",
    ) -> None:
        self._primary_engine = primary_engine
        self._fallback_engine = fallback_engine

    def decide(
        self, page,  # type: ignore[name-defined]
    ) -> "OcrPolicyDecision":
        if page.native_text_present and not page.ocr_used:
            return OcrPolicyDecision(
                page_no=page.page_no, should_ocr=False,
                reason="native_text_present",
                candidate_engine=self._primary_engine,
            )
        if page.ocr_used:
            return OcrPolicyDecision(
                page_no=page.page_no, should_ocr=False,
                reason="already_ocr_used",
                candidate_engine=self._primary_engine,
            )
        return OcrPolicyDecision(
            page_no=page.page_no, should_ocr=True,
            reason="no_native_text",
            candidate_engine=self._primary_engine,
        )

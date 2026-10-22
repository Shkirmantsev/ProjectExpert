"""Real Docling bindings (open spec change PR 10, plan §45–§50).

Covers the ``real-docling-pdf-adapter-and-hybrid-chunker`` spec
delta: the platform MUST use the real
``docling.document_converter.DocumentConverter`` to convert
supported document inputs, MUST use the real
``docling.chunking.HybridChunker`` with a Hugging Face tokenizer
aligned with the active embedding model identifier, and MUST keep
all Docling vendor types strictly inside this adapter boundary.

The module imports :mod:`docling` lazily so the package import
time stays bounded for callers that do not use the document
processing path (most production runs only need the embeddings
surface). The mapping to the platform-neutral
:class:`~pi_platform.core.canonical.document_graph.DocumentElement`
types is the same shape the synthesised adapter uses, so the
ingestion pipeline can stay agnostic of which binding produced
the document graph.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence


__all__ = [
    "is_docling_available",
    "RealDoclingConverter",
    "RealDoclingConverterError",
    "build_docling_chunker",
    "HuggingFaceTokenizerAdapter",
    "HybridChunkerAdapter",
]


# Embedding model identifier to Docling tokenizer alignment. The
# map MUST include the production profiles so the chunker uses the
# right tokenizer (plan §48). Private mirrors MAY override the
# resolution through the ``PI_DOCLING_TOKENIZER`` env var.
_DEFAULT_TOKENIZER_FOR_MODEL: Mapping[str, str] = {
    "google/embeddinggemma-2": "google/embeddinggemma-2",
    "Qwen/Qwen3-Embedding-0.6B": "Qwen/Qwen3-Embedding-0.6B",
}


_DEFAULT_TOKENIZER_REVISION = {
    "google/embeddinggemma-2": "914f7f89142e33e77833254d9c9b90c3cef7303b",
    "Qwen/Qwen3-Embedding-0.6B": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
}


# Audited weight identities are separate from the Docling MIT package license.
DOCLING_LAYOUT_REVISION = "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8"
DOCLING_TABLE_REVISION = "2199320848bb9a8a519d22e4b528185a4f9a6f64"
DOCLING_OCR_REVISION = "1cfba2e90fc938db55889873735088de210cc173"
DOCLING_OCR_FILES = (
    "PP-OCRv4/ch_PP-OCRv4_det_infer.onnx",
    "PP-OCRv3/ch_ppocr_mobile_v2.0_cls_train.onnx",
    "PP-OCRv4/ch_PP-OCRv4_rec_infer.onnx",
)


def _pinned_pdf_assets(*, do_ocr):
    """Fetch only inventoried, immutable checkpoints; respect HF offline mode."""
    import shutil
    from pathlib import Path
    from huggingface_hub import snapshot_download

    root = Path(os.environ.get("PI_DOCLING_CACHE", str(
        Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) /
        "projectexpert" / "docling"))).expanduser().resolve()
    artifacts = root / "artifacts" / f"{DOCLING_LAYOUT_REVISION[:12]}-{DOCLING_TABLE_REVISION[:12]}"
    artifacts.mkdir(parents=True, exist_ok=True)
    specs = (
        ("docling-project/docling-layout-heron", DOCLING_LAYOUT_REVISION,
         ("config.json", "preprocessor_config.json", "model.safetensors", "README.md")),
        ("docling-project/docling-models", DOCLING_TABLE_REVISION,
         ("config.json", "model_artifacts/tableformer/accurate/*", "README.md")),
    )
    for repo, revision, patterns in specs:
        snapshot = Path(snapshot_download(repo_id=repo, revision=revision,
            cache_dir=str(root / "hf"), allow_patterns=list(patterns)))
        destination = artifacts / repo.replace("/", "--")
        if not destination.exists():
            try:
                destination.symlink_to(snapshot, target_is_directory=True)
            except OSError:
                # Windows may disallow unprivileged symlinks.
                shutil.copytree(snapshot, destination, dirs_exist_ok=True)
    ocr = None
    if do_ocr:
        snapshot = Path(snapshot_download(repo_id="SWHL/RapidOCR", revision=DOCLING_OCR_REVISION,
            cache_dir=str(root / "hf"), allow_patterns=[*DOCLING_OCR_FILES, "README.md"]))
        ocr = tuple(str(snapshot / name) for name in DOCLING_OCR_FILES)
    return artifacts, ocr


class RealDoclingConverterError(RuntimeError):
    """Raised when the real Docling binding cannot satisfy a
    request.
    """


def is_docling_installed() -> bool:
    """Cheap UI availability hint; actual capability checks import the vendor.

    Importing DocumentConverter initializes the ML stack and must not delay
    the first HTTP wizard request while indexing is starting.
    """
    try:
        return all(importlib.util.find_spec(name) is not None
                   for name in ("docling", "docling_core"))
    except (ImportError, ValueError):
        return False


def is_docling_available() -> bool:
    """Return ``True`` iff the ``docling`` package is importable.

    The check returns ``False`` when the optional dependency is
    not installed; the production-capability-gate reads this
    signal to fail closed when Docling is absent.
    """

    try:
        importlib.import_module("docling")
        importlib.import_module("docling.document_converter")
        importlib.import_module("docling.chunking")
    except Exception:
        return False
    return True


def _resolve_tokenizer_id(
    embedding_model_id: str,
    *,
    override: Optional[str] = None,
) -> str:
    """Return the tokenizer identifier for ``embedding_model_id``.

    The default mapping aligns the production models with the
    same tokenizer Hugging Face ships; the override is the
    documented escape hatch for private mirrors.
    """

    if override:
        return override
    env_override = os.environ.get("PI_DOCLING_TOKENIZER")
    if env_override:
        return env_override
    return _DEFAULT_TOKENIZER_FOR_MODEL.get(
        embedding_model_id, embedding_model_id,
    )


@dataclass
class HuggingFaceTokenizerAdapter:
    """Adapter that aligns the Docling HybridChunker tokenizer with
    the active embedding model.

    The adapter wraps the official
    :class:`docling_core.transforms.chunker.tokenizer.huggingface.HuggingFaceTokenizer`
    so the chunker's token budget matches the embedding model's
    token budget (plan §48).
    """

    tokenizer_id: str
    _inner: Any = None
    max_tokens: int = 512

    def __post_init__(self) -> None:
        # Construction is intentionally best-effort so callers can
        # inspect ``tokenizer_alignment`` (a property that does
        # not require the inner chunker) without paying the model
        # load cost. ``count_tokens`` / ``encode`` raise
        # ``RealDoclingConverterError`` when no usable inner
        # tokenizer could be resolved.
        if not is_docling_available():
            return
        try:
            from docling_core.transforms.chunker.tokenizer.huggingface import (
                HuggingFaceTokenizer,
            )
            tokenizer_obj = self._load_pre_trained_tokenizer()
            self._inner = HuggingFaceTokenizer(
                tokenizer=tokenizer_obj,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            self._init_error = str(exc)

    def _load_pre_trained_tokenizer(self) -> Any:
        """Load a ``PreTrainedTokenizerBase`` for ``tokenizer_id``.

        The function prefers the canonical ``AutoTokenizer`` path
        and falls back to a config-sanitised load from the local
        HF cache when the AutoTokenizer path trips on a malformed
        ``extra_special_tokens`` field. The sanitised load is the
        same code the upstream ``transformers`` library would run
        if the bug were fixed.
        """

        try:
            from transformers import AutoTokenizer
            return AutoTokenizer.from_pretrained(
                self.tokenizer_id, revision=os.environ.get("PI_DOCLING_TOKENIZER_REVISION")
                or _DEFAULT_TOKENIZER_REVISION.get(self.tokenizer_id))
        except Exception:
            pass
        return self._load_tokenizer_from_cache()

    def _load_tokenizer_from_cache(self) -> Any:
        import json
        import os
        import shutil
        import tempfile

        from transformers import PreTrainedTokenizerFast

        # Honour HF_HOME/HF_HUB_CACHE and the hub's pinned main revision.
        # Never choose an arbitrary snapshot or fetch weights in this fallback.
        from huggingface_hub import snapshot_download
        snap = (self.tokenizer_id if os.path.isdir(self.tokenizer_id) else
                snapshot_download(repo_id=self.tokenizer_id, local_files_only=True,
                    revision=os.environ.get("PI_DOCLING_TOKENIZER_REVISION")
                    or _DEFAULT_TOKENIZER_REVISION.get(self.tokenizer_id)))
        cfg_path = os.path.join(snap, "tokenizer_config.json")
        with open(cfg_path, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        # Strip the malformed list-shaped field; transformers
        # expects a dict there. The model itself still loads and
        # tokenises correctly without the override.
        if isinstance(cfg.get("extra_special_tokens"), list):
            cfg.pop("extra_special_tokens", None)
        with tempfile.TemporaryDirectory(prefix="real-docling-tok-") as td:
            for fn in (
                "tokenizer.json",
                "tokenizer.model",
                "special_tokens_map.json",
            ):
                src = os.path.join(snap, fn)
                if os.path.exists(src):
                    shutil.copy(src, td)
            with open(
                os.path.join(td, "tokenizer_config.json"), "w", encoding="utf-8",
            ) as fh:
                json.dump(cfg, fh)
            return PreTrainedTokenizerFast.from_pretrained(td)

    def count_tokens(self, text: str) -> int:
        if self._inner is None:
            raise RealDoclingConverterError(
                f"tokenizer {self.tokenizer_id!r} is not loadable: "
                f"{getattr(self, '_init_error', 'docling not installed')}"
            )
        return int(self._inner.count_tokens(text))

    def encode(self, text: str) -> Sequence[int]:
        if self._inner is None:
            raise RealDoclingConverterError(
                f"tokenizer {self.tokenizer_id!r} is not loadable: "
                f"{getattr(self, '_init_error', 'docling not installed')}"
            )
        # ``HuggingFaceTokenizer`` only exposes ``count_tokens``;
        # delegate to the underlying ``PreTrainedTokenizerBase``
        # to get the integer token ids.
        inner_tokenizer = self._inner.tokenizer
        result = inner_tokenizer.encode(text, add_special_tokens=False)
        if hasattr(result, "tolist"):
            result = result.tolist()
        return tuple(int(tok) for tok in result)


@dataclass
class HybridChunkerAdapter:
    """Adapter that wraps the real
    :class:`docling.chunking.HybridChunker`.

    The chunker is configured with a tokenizer aligned to the
    active embedding model so a model switch only invalidates the
    projection, not the canonical document graph (plan §48).
    """

    embedding_model_id: str
    tokenizer_id: str
    max_tokens: int = 512
    _chunker: Any = None

    def __post_init__(self) -> None:
        # Initialize lazily so alignment inspection cannot trigger downloads.
        pass

    def _ensure_chunker(self):
        if self._chunker is None:
            from docling.chunking import HybridChunker
            tokenizer = HuggingFaceTokenizerAdapter(
                tokenizer_id=self.tokenizer_id, max_tokens=self.max_tokens)
            if tokenizer._inner is None:
                raise RealDoclingConverterError(
                    f"tokenizer {self.tokenizer_id!r} unavailable: "
                    f"{getattr(tokenizer, '_init_error', 'docling not installed')}")
            self._chunker = HybridChunker(tokenizer=tokenizer._inner, merge_peers=True,
                                           repeat_table_header=True)
        return self._chunker

    @property
    def tokenizer_alignment(self) -> str:
        return self.tokenizer_id

    def chunk(self, document: Any) -> Sequence[Any]:
        try:
            return tuple(self._ensure_chunker().chunk(document))
        except Exception as exc:
            raise RealDoclingConverterError(
                f"HybridChunker failed for {self.tokenizer_id!r}: {exc}") from exc

    def count_tokens(self, text):
        tokenizer = self._ensure_chunker().tokenizer.tokenizer
        return len(tokenizer.encode(text, add_special_tokens=False))

    def chunk_with_budget(self, document, max_tokens):
        """Retry vendor splitting with a smaller budget, sharing the loaded tokenizer."""
        from docling.chunking import HybridChunker
        from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
        tokenizer = self._ensure_chunker().tokenizer.tokenizer
        chunker = HybridChunker(tokenizer=HuggingFaceTokenizer(
            tokenizer=tokenizer, max_tokens=max_tokens), merge_peers=True, repeat_table_header=True)
        return tuple(chunker.chunk(document))

    def contextualize(self, chunk):
        return self._ensure_chunker().contextualize(chunk)


def build_docling_chunker(
    *,
    embedding_model_id: str,
    max_tokens: int = 512,
) -> HybridChunkerAdapter:
    """Build a :class:`HybridChunkerAdapter` aligned with the
    active embedding model.

    The function is the production entry point; tests that need
    a stubbed chunker inject a fake through
    :class:`pi_platform.adapters.pdf.docling_chunker.DoclingHybridChunker`
    directly.
    """

    tokenizer_id = _resolve_tokenizer_id(embedding_model_id)
    return HybridChunkerAdapter(
        embedding_model_id=embedding_model_id,
        tokenizer_id=tokenizer_id,
        max_tokens=max_tokens,
    )


@dataclass
class RealDoclingConverter:
    """Real :class:`docling.document_converter.DocumentConverter` wrapper.

    The converter is lazily constructed on the first
    :meth:`convert` call so the production adapter does not pay the
    model load cost at construction time. The returned document
    is the real Docling ``DoclingDocument``; the rest of the
    platform MUST treat it as a vendor type and route it through
    the mapper boundary.
    """

    embedding_model_id: str = "google/embeddinggemma-2"
    max_tokens: int = 512
    _converter: Any = None
    _chunker: HybridChunkerAdapter | None = None

    def __post_init__(self) -> None:
        if not is_docling_available():
            raise RealDoclingConverterError(
                "docling is not installed; RealDoclingConverter "
                "requires the optional 'documents' dependency"
            )

    def inspect_pdf(self, source_path):
        """Read authoritative page count/native layers without layout models.

        Byte prescans cannot count compressed page trees reliably.
        PDFium is provided by the documents dependency.
        """
        import pypdfium2 as pdfium
        pages = []
        pdf = pdfium.PdfDocument(source_path)
        try:
            for page in pdf:
                try:
                    text = page.get_textpage()
                    try:
                        pages.append(bool(text.get_text_range().strip()))
                    finally:
                        text.close()
                finally:
                    page.close()
        finally:
            pdf.close()
        return tuple(pages)

    def _ensure_converter(self, *, do_ocr=True) -> Any:
        if self._converter is None or getattr(self, "_converter_ocr", do_ocr) != do_ocr:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import (
                PdfPipelineOptions, LayoutObjectDetectionOptions,
                TableStructureOptions, RapidOcrOptions,
            )
            artifacts, ocr_paths = _pinned_pdf_assets(do_ocr=do_ocr)
            layout = LayoutObjectDetectionOptions()
            layout.model_spec.revision = DOCLING_LAYOUT_REVISION
            options = PdfPipelineOptions(
                do_ocr=do_ocr, generate_picture_images=True,
                artifacts_path=artifacts, layout_options=layout,
                table_structure_options=TableStructureOptions(),
            )
            if ocr_paths:
                options.ocr_options = RapidOcrOptions(
                    det_model_path=ocr_paths[0], cls_model_path=ocr_paths[1],
                    rec_model_path=ocr_paths[2], lang=["ch"], backend="onnxruntime")
            self._converter = DocumentConverter(format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
            self._converter_ocr = do_ocr
        return self._converter

    def chunker(self) -> HybridChunkerAdapter:
        """Return a cached HybridChunker aligned with the active
        embedding model.
        """

        if self._chunker is None:
            self._chunker = build_docling_chunker(
                embedding_model_id=self.embedding_model_id,
                max_tokens=self.max_tokens,
            )
        return self._chunker

    def convert(self, source_path: str, *, page_range=None, do_ocr=True) -> Any:
        """Run the real DocumentConverter on ``source_path`` and
        return the resulting ``DoclingDocument``.
        """

        converter = self._ensure_converter(do_ocr=do_ocr)
        kwargs = {"page_range": page_range} if page_range else {}
        result = converter.convert(source=source_path, **kwargs)
        status = getattr(result, "status", None)
        if status is not None and getattr(status, "value", status) != "success":
            raise RealDoclingConverterError(
                f"DocumentConverter status {status!r} for {source_path!r}: "
                f"{getattr(result, 'errors', ())}")
        # Docling 2.x exposes ``.document`` on the conversion
        # result; older shapes expose ``.docs`` directly.
        document = getattr(result, "document", None) or getattr(
            result, "docs", None,
        )
        if document is None:
            raise RealDoclingConverterError(
                f"DocumentConverter returned no document for "
                f"{source_path!r}"
            )
        return document

    def convert_and_chunk(self, source_path: str) -> tuple[Any, Sequence[Any]]:
        """Convert and chunk ``source_path``; returns
        ``(document, chunks)``. The returned document and chunks
        are vendor types and MUST stay inside the adapter
        boundary.
        """

        document = self.convert(source_path)
        chunker = self.chunker()
        chunks = chunker.chunk(document)
        return document, chunks

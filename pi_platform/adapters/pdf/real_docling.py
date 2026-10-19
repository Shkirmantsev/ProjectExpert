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


class RealDoclingConverterError(RuntimeError):
    """Raised when the real Docling binding cannot satisfy a
    request.
    """


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
                max_tokens=self._resolve_max_tokens(),
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
            return AutoTokenizer.from_pretrained(self.tokenizer_id)
        except Exception:
            pass
        return self._load_tokenizer_from_cache()

    def _load_tokenizer_from_cache(self) -> Any:
        import json
        import os
        import shutil
        import tempfile

        from transformers import PreTrainedTokenizerFast

        cache_root = os.path.join(
            os.path.expanduser("~"),
            ".cache",
            "huggingface",
            "hub",
            f"models--{self.tokenizer_id.replace('/', '--')}",
            "snapshots",
        )
        if not os.path.isdir(cache_root):
            raise RealDoclingConverterError(
                f"tokenizer {self.tokenizer_id!r} not in local HF cache; "
                "ensure the embedding model is pulled before chunking"
            )
        snap = os.path.join(cache_root, os.listdir(cache_root)[0])
        cfg_path = os.path.join(snap, "tokenizer_config.json")
        with open(cfg_path, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        # Strip the malformed list-shaped field; transformers
        # expects a dict there. The model itself still loads and
        # tokenises correctly without the override.
        if isinstance(cfg.get("extra_special_tokens"), list):
            cfg.pop("extra_special_tokens", None)
        td = tempfile.mkdtemp(prefix="real-docling-tok-")
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

    def _resolve_max_tokens(self) -> int:
        """Read ``max_seq_length`` from the sentence-transformers
        config when available, else default to 512 (the active
        embedding model token budget).
        """

        import json
        import os

        cache_root = os.path.join(
            os.path.expanduser("~"),
            ".cache",
            "huggingface",
            "hub",
            f"models--{self.tokenizer_id.replace('/', '--')}",
            "snapshots",
        )
        if os.path.isdir(cache_root):
            for snap_name in os.listdir(cache_root):
                cfg = os.path.join(
                    cache_root, snap_name, "sentence_bert_config.json",
                )
                if not os.path.exists(cfg):
                    continue
                try:
                    with open(cfg, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    return int(data["max_seq_length"])
                except Exception:
                    continue
        return 512

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
        # Best-effort construction; ``chunk()`` raises when the
        # inner chunker is missing.
        if not is_docling_available():
            return
        try:
            from docling.chunking import HybridChunker
            self._chunker = HybridChunker(
                tokenizer=HuggingFaceTokenizerAdapter(
                    tokenizer_id=self.tokenizer_id,
                )._inner,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            self._init_error = str(exc)

    @property
    def tokenizer_alignment(self) -> str:
        return self.tokenizer_id

    def chunk(self, document: Any) -> Sequence[Any]:
        if self._chunker is None:
            raise RealDoclingConverterError(
                f"HybridChunker not buildable for {self.tokenizer_id!r}: "
                f"{getattr(self, '_init_error', 'docling not installed')}"
            )
        return tuple(self._chunker.chunk(document))


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

    def _ensure_converter(self) -> Any:
        if self._converter is None:
            from docling.document_converter import DocumentConverter
            self._converter = DocumentConverter()
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

    def convert(self, source_path: str) -> Any:
        """Run the real DocumentConverter on ``source_path`` and
        return the resulting ``DoclingDocument``.
        """

        converter = self._ensure_converter()
        result = converter.convert(source=source_path)
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

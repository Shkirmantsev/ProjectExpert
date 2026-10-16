"""JSON corpus loader for the v0.8 Tier-3 evaluation command.

Package J's ``evals/corpus/{synthetic,generated-pdf,multilingual,
java,requirements}/corpus.json`` files describe the sub-corpora
the Tier-3 retrieval evaluator indexes. The loader reads each
JSON file into a list of corpus chunk records and exposes a
small builder that materialises the canonical
:class:`RetrievalHit` value type for the multi-stage pipeline.

The loader never reaches into third-party PDF / Java /
multilingual libraries; the generated-pdf sub-corpus is
served by the ``DoclingPdfAdapter`` STUB which synthesises a
``_DoclingDocument`` from the prescan, and the Java /
multilingual / requirements sub-corpora are read directly from
the JSON manifests. The loader is the single seam where the
in-tree eval fixtures meet the runtime retrieval ports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import (
    KnowledgeState,
    Metadata,
)
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit


__all__ = [
    "CORPUS_FILE_NAME",
    "CorpusChunk",
    "CorpusLoadError",
    "build_pipeline_hits",
    "load_corpus_json",
]


CORPUS_FILE_NAME = "corpus.json"


@dataclass(frozen=True)
class CorpusChunk:
    """One sanitised chunk from a JSON corpus file.

    The fields mirror the JSON manifest schema
    (``chunk_id``, ``document_id``, ``text``, ``language``,
    ``valid_from``). Optional fields default to safe values
    so a manifest can omit them without breaking the loader.
    """

    chunk_id: str
    document_id: str
    text: str
    language: str = "en"
    valid_from: str = "2026-01-01"
    # Optional field used by the generated-pdf sub-corpus to
    # tag chunks that came from a prescan (rather than a
    # native JSON chunk). Defaults to ``False``.
    from_pdf_prescan: bool = False


class CorpusLoadError(RuntimeError):
    """Raised when a JSON corpus file cannot be loaded."""


def load_corpus_json(
    corpus_dir: Path | str,
    *,
    file_name: str = CORPUS_FILE_NAME,
) -> tuple[CorpusChunk, ...]:
    """Load a JSON corpus file from ``corpus_dir``.

    The default file name is ``corpus.json``; an operator can
    point at a different file (e.g. a confidential corpus
    under ``tmp/local/evals/``) by passing ``file_name``.
    """

    path = Path(corpus_dir) / file_name
    if not path.exists():
        raise CorpusLoadError(f"corpus file not found: {path!s}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusLoadError(
            f"corpus file at {path!s} is not valid JSON: {exc}"
        ) from exc
    return parse_corpus_payload(payload, source=str(path))


def parse_corpus_payload(
    payload: object,
    *,
    source: str = "<memory>",
) -> tuple[CorpusChunk, ...]:
    """Parse an already-loaded JSON payload into corpus chunks."""
    if not isinstance(payload, Mapping):
        raise CorpusLoadError(
            f"corpus at {source} must be a JSON object at the top "
            f"level, got {type(payload).__name__}"
        )
    raw_chunks = payload.get("chunks")
    if not isinstance(raw_chunks, list):
        raise CorpusLoadError(
            f"corpus at {source} must define a 'chunks' list, got "
            f"{type(raw_chunks).__name__}"
        )
    out: list[CorpusChunk] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_chunks):
        if not isinstance(raw, Mapping):
            raise CorpusLoadError(
                f"corpus {source} entry #{index} must be a mapping, "
                f"got {type(raw).__name__}"
            )
        chunk_id = str(raw.get("chunk_id") or "").strip()
        if not chunk_id:
            raise CorpusLoadError(
                f"corpus {source} entry #{index} is missing a "
                f"non-empty 'chunk_id'"
            )
        if chunk_id in seen:
            raise CorpusLoadError(
                f"corpus {source} has duplicate chunk_id "
                f"{chunk_id!r}"
            )
        seen.add(chunk_id)
        document_id = str(raw.get("document_id") or chunk_id).strip()
        text = str(raw.get("text") or "")
        if not text.strip():
            raise CorpusLoadError(
                f"corpus {source} chunk {chunk_id!r} has no 'text'"
            )
        out.append(CorpusChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            text=text,
            language=str(raw.get("language") or "en"),
            valid_from=str(raw.get("valid_from") or "2026-01-01"),
            from_pdf_prescan=bool(raw.get("from_pdf_prescan", False)),
        ))
    return tuple(out)


def build_pipeline_hits(
    chunks: Iterable[CorpusChunk],
) -> list[RetrievalHit]:
    """Materialise a list of :class:`RetrievalHit` for the pipeline.

    The hits carry the source ``"dense"`` placeholder so the
    hybrid retrieval layer picks them up as dense candidates;
    the Tier-3 evaluator's hash-based scoring determines the
    final ranking. ``KnowledgeState.VERIFIED`` is the
    authoritative state for every corpus chunk; the
    ``evidenceWeight`` is 1.0 because the corpus chunks are
    sanitised ground-truth fixtures, not user-supplied
    content.
    """

    hits: list[RetrievalHit] = []
    for chunk in chunks:
        md = Metadata(
            documentId=chunk.document_id,
            version="0.8.0",
            language=chunk.language,
            validFrom=chunk.valid_from,
            validTo="",
            gitCommit="",
            sourcePath=f"evals/corpus/{chunk.document_id}",
            securityClassification="",
        )
        hits.append(RetrievalHit(
            chunkId=chunk.chunk_id,
            score=0.0,
            source="dense",
            snippet=chunk.text,
            contentHash=chunk.chunk_id,
            metadata=md,
            knowledgeState=KnowledgeState.VERIFIED,
            tokenEstimate=max(1, len(chunk.text) // 4),
            evidenceWeight=1.0,
        ))
    return hits

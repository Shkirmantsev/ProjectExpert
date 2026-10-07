"""Default :class:`SparseIndexPort` implementation (in-process BM25).

The implementation keeps the term-frequency / inverse-document-
frequency tables in memory and rebuilds incrementally as documents are
added or removed. The implementation does NOT require the optional
``rank-bm25`` MIT library; it is a self-contained BM25 scoring
function.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Sequence

from pi_platform.ports.runtime.sparse_index import (
    SparseHit,
    SparseIndexPort,
)


__all__ = ["Bm25SparseIndex"]


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class _DocumentState:
    family: str
    text: str
    metadata: Mapping[str, object] = field(default_factory=dict)
    length: int = 0
    tf: Counter = field(default_factory=Counter)


class Bm25SparseIndex(SparseIndexPort):
    """In-process BM25 sparse index."""

    def __init__(self, *, k1: float = 1.5, b: float = 0.75):
        self._k1 = k1
        self._b = b
        self._docs: Dict[str, _DocumentState] = {}
        self._df: Counter = Counter()
        self._avgdl: float = 0.0
        self._total_len: int = 0

    def _recompute_avgdl(self) -> None:
        if not self._docs:
            self._avgdl = 0.0
            return
        self._avgdl = self._total_len / len(self._docs)

    def _metadata_bonus(self, query_metadata: Mapping[str, object],
                        doc_metadata: Mapping[str, object]) -> float:
        if not query_metadata:
            return 0.0
        bonus = 0.0
        for key, value in query_metadata.items():
            if doc_metadata.get(key) == value:
                bonus += 0.5
        return bonus

    def index_document(
        self, family: str, documentId: str, text: str,
        metadata: Mapping[str, object],
    ) -> None:
        if documentId in self._docs:
            self.delete_document(documentId)
        tokens = _tokenize(text)
        tf = Counter(tokens)
        state = _DocumentState(
            family=family,
            text=text,
            metadata=dict(metadata),
            length=len(tokens),
            tf=tf,
        )
        self._docs[documentId] = state
        for term in tf.keys():
            self._df[term] += 1
        self._total_len += state.length
        self._recompute_avgdl()

    def delete_document(self, documentId: str) -> None:
        state = self._docs.pop(documentId, None)
        if state is None:
            return
        for term in state.tf.keys():
            self._df[term] -= 1
            if self._df[term] <= 0:
                self._df.pop(term, None)
        self._total_len -= state.length
        self._recompute_avgdl()

    def query(
        self, text: str, top_k: int = 10,
        metadata: Optional[Mapping[str, object]] = None,
    ) -> Sequence[SparseHit]:
        if not self._docs:
            return ()
        query_tokens = _tokenize(text)
        if not query_tokens:
            return ()
        n_docs = len(self._docs)
        avgdl = self._avgdl or 1.0
        scores: list[tuple[str, float]] = []
        for doc_id, state in self._docs.items():
            score = 0.0
            for term in query_tokens:
                if term not in state.tf:
                    continue
                df = self._df.get(term, 0)
                idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
                tf = state.tf[term]
                denom = tf + self._k1 * (
                    1 - self._b + self._b * state.length / avgdl
                )
                score += idf * (tf * (self._k1 + 1)) / denom
            score += self._metadata_bonus(metadata or {}, state.metadata)
            if score > 0:
                scores.append((doc_id, score))
        scores.sort(key=lambda x: (-x[1], x[0]))
        hits: list[SparseHit] = []
        for doc_id, score in scores[:top_k]:
            snippet = self._snippet(self._docs[doc_id].text, query_tokens)
            hits.append(SparseHit(documentId=doc_id, score=score, snippet=snippet))
        return tuple(hits)

    def _snippet(self, text: str, query_tokens: Sequence[str]) -> str:
        if not query_tokens:
            return text[:120]
        lower = text.lower()
        for tok in query_tokens:
            idx = lower.find(tok)
            if idx >= 0:
                start = max(0, idx - 20)
                end = min(len(text), idx + 80)
                return text[start:end]
        return text[:120]

    def stats(self) -> Mapping[str, int]:
        return {
            "documents": len(self._docs),
            "terms": len(self._df),
            "bytes": sum(len(s.text) for s in self._docs.values()),
        }
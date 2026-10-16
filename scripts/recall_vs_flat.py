#!/usr/bin/env python3
"""Measure USearch ANN recall against the FlatDenseIndex baseline (Change Package D).

Usage:
  python3 scripts/recall_vs_flat.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pi_platform.adapters.retrieval.hashing_embedding_model import (  # noqa: E402
    HashingEmbeddingAdapter,
)
from pi_platform.adapters.runtime.flat_dense_index import (  # noqa: E402
    FlatDenseIndex,
)
from pi_platform.adapters.runtime.usearch_dense_index import (  # noqa: E402
    USearchDenseIndex,
)
from pi_platform.ports.retrieval.embedding_profile import (  # noqa: E402
    HASHING_DEFAULT,
)


__all__ = ["measure_recall_vs_flat", "main"]


def measure_recall_vs_flat(
    *,
    corpus_size: int = 128,
    queries_count: int = 16,
    top_k: int = 10,
) -> dict[str, object]:
    """Compare USearchDenseIndex top-k hits against FlatDenseIndex."""
    embedder = HashingEmbeddingAdapter(dimension=64)
    flat = FlatDenseIndex()
    with tempfile.TemporaryDirectory() as tmp:
        usearch = USearchDenseIndex(
            embedding_profile_hash=HASHING_DEFAULT.identity(),
            cache_root=tmp,
        )
        for i in range(corpus_size):
            chunk_id = f"chunk-{i:04d}"
            vec = tuple(embedder.embed(f"protocol message variant {i} ILO-{5000 + i}"))
            flat.index_chunk(chunk_id, vec, metadata={"doc": chunk_id})
            usearch.index_chunk(chunk_id, vec, metadata={"doc": chunk_id})
        recalls: list[float] = []
        for q in range(queries_count):
            qvec = tuple(embedder.embed(f"protocol message variant {q * 3}"))
            flat_ids = {h.chunkId for h in flat.query(qvec, top_k=top_k)}
            ann_ids = {h.chunkId for h in usearch.query(qvec, top_k=top_k)}
            recalls.append(len(flat_ids & ann_ids) / max(1, len(flat_ids)))
    mean_recall = sum(recalls) / max(1, len(recalls))
    return {
        "ok": True,
        "corpus_size": corpus_size,
        "queries_count": queries_count,
        "top_k": top_k,
        "recall_vs_flat": mean_recall,
    }


def main() -> int:
    payload = measure_recall_vs_flat()
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

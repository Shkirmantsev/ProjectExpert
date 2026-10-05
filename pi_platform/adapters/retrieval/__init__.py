"""Phase 4 retrieval adapters for the v0.8 Project Intelligence Platform.

The adapter layer binds the Phase 4 core to concrete backends:
hashing / multilingual sentence-transformers embeddings, RRF
hybrid composition, identifier-recognition, BM25-light reranker,
metadata-driven filters, the context assembler and the production
graph-expansion adapter that replaces the Phase 3 stub.
"""

from __future__ import annotations


__all__: list[str] = []
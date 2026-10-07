"""Phase 4 retrieval ports for the v0.8 Project Intelligence Platform.

Covers architecture sections §25-§33 (embedding model, sparse /
exact retrieval, hybrid retrieval, ANN candidate generation, multi-
stage retrieval, optional advanced reranking, graph expansion,
context assembler, retrieval-first agent access strategy).

The Phase 4 retrieval ports compose the Phase 3 storage layer
(:mod:`pi_platform.ports.runtime`) and feed the Phase 5 orchestrator
and Phase 6 MCP server.
"""

from __future__ import annotations

from pi_platform.ports.retrieval.context_assembler import (
    Citation,
    ContextAssemblerPort,
    ContextAssemblerError,
    ContextBundle,
    ContextBudget,
)
from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelPort,
    EmbeddingModelError,
)
from pi_platform.ports.retrieval.hybrid_retrieval import (
    HybridRetrievalPort,
    HybridRetrievalError,
    RetrievalHit,
)
from pi_platform.ports.retrieval.metadata_filter import (
    DropReason,
    MetadataFilter,
    MetadataFilterPort,
    MetadataFilterError,
)
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalPort,
    MultiStageRetrievalError,
    RetrievalQuery,
    RetrievalResult,
    StageReport,
)
from pi_platform.ports.retrieval.reranker import (
    RerankerPort,
    RerankerError,
)


__all__ = [
    "Citation",
    "ContextAssemblerError",
    "ContextAssemblerPort",
    "ContextBundle",
    "ContextBudget",
    "DropReason",
    "EmbeddingModelError",
    "EmbeddingModelPort",
    "HybridRetrievalError",
    "HybridRetrievalPort",
    "MetadataFilter",
    "MetadataFilterError",
    "MetadataFilterPort",
    "MultiStageRetrievalError",
    "MultiStageRetrievalPort",
    "RetrievalHit",
    "RetrievalQuery",
    "RetrievalResult",
    "RerankerError",
    "RerankerPort",
    "StageReport",
]
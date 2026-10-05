"""Aggregate public interface for the Phase 3 runtime ports."""

from .dense_index import DenseHit, DenseIndexError, DenseIndexPort
from .freshness import (
    FreshnessError,
    FreshnessFact,
    FreshnessSnapshot,
    FreshnessTrackerPort,
)
from .full_text_index import (
    FullTextHit,
    FullTextIndexError,
    FullTextIndexPort,
)
from .graph import GraphManifest, GraphPort, GraphPortError
from .graph_expansion import (
    GraphExpansion,
    GraphExpansionError,
    GraphExpansionPort,
)
from .provenance import (
    ProvenanceError,
    ProvenanceEvent,
    ProvenancePort,
)
from .runtime_store import (
    ContentAddressCollision,
    KnowledgeStatePolicy,
    ProjectLockTimeout,
    RuntimeEntry,
    RuntimeStatusReport,
    RuntimeStoreError,
    RuntimeStorePort,
    VersionStampMismatch,
    WALTailCorrupt,
)
from .sparse_index import SparseHit, SparseIndexError, SparseIndexPort


__all__ = [
    "ContentAddressCollision",
    "DenseHit",
    "DenseIndexError",
    "DenseIndexPort",
    "FreshnessError",
    "FreshnessFact",
    "FreshnessSnapshot",
    "FreshnessTrackerPort",
    "FullTextHit",
    "FullTextIndexError",
    "FullTextIndexPort",
    "GraphExpansion",
    "GraphExpansionError",
    "GraphExpansionPort",
    "GraphManifest",
    "GraphPort",
    "GraphPortError",
    "KnowledgeStatePolicy",
    "ProjectLockTimeout",
    "ProvenanceError",
    "ProvenanceEvent",
    "ProvenancePort",
    "RuntimeEntry",
    "RuntimeStatusReport",
    "RuntimeStoreError",
    "RuntimeStorePort",
    "SparseHit",
    "SparseIndexError",
    "SparseIndexPort",
    "VersionStampMismatch",
    "WALTailCorrupt",
]
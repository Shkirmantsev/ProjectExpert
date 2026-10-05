"""Aggregate public interface for the Phase 3 runtime adapters.

The :mod:`.graph_expansion` module exposes the Phase 4 production
graph-expansion adapter that replaces the Phase 3 stub
(:class:`BoundedGraphExpansion`). Both adapters implement the
same :class:`GraphExpansionPort` contract so Phase 3 regression
tests keep their binding while Phase 4 production code uses the
deeper implementation.
"""

from .bm25_sparse_index import Bm25SparseIndex
from .bounded_graph_expansion import BoundedGraphExpansion
from .flat_dense_index import FlatDenseIndex
from .graph_expansion import ProductionGraphExpansion
from .last_verified_freshness_tracker import LastVerifiedFreshnessTracker
from .provenance_tracker import LocalProvenanceTracker
from .sharded_graph import LocalShardedGraph
from .sqlite_fts_full_text_index import SqliteFtsFullTextIndex
from .sqlite_runtime_store import SqliteRuntimeStore


__all__ = [
    "Bm25SparseIndex",
    "BoundedGraphExpansion",
    "FlatDenseIndex",
    "LastVerifiedFreshnessTracker",
    "LocalProvenanceTracker",
    "LocalShardedGraph",
    "ProductionGraphExpansion",
    "SqliteFtsFullTextIndex",
    "SqliteRuntimeStore",
]
"""In-memory :class:`RetrievalTraceStorePort` implementation.

Change Package I of the v0.8 refinement ships an in-memory trace
store bounded by :data:`DEFAULT_TRACE_STORE_LIMIT` records. The
FIFO bound keeps the debug-only trace store from growing without
limit; the lock makes the store safe to call from the asyncio
event loop the MCP server uses.

The store is intentionally tiny: it only knows how to put, fetch,
list and evict records. The MCP tool :func:`McpServer.get_retrieval_trace`
serialises the trace through
:meth:`RetrievalTraceBuilder.to_json` so secret metadata is
redacted before the record leaves the process boundary.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Optional, Sequence

from pi_platform.core.retrieval.retrieval_trace import RetrievalTrace
from pi_platform.ports.retrieval.trace_store import (
    DEFAULT_TRACE_STORE_LIMIT,
    RetrievalTraceRecord,
    RetrievalTraceStorePort,
)


__all__ = ["InMemoryRetrievalTraceStore", "compute_trace_id"]


class InMemoryRetrievalTraceStore(RetrievalTraceStorePort):
    """Thread-safe FIFO in-memory retrieval trace store.

    The store keeps at most ``capacity`` records. When the bound
    is exceeded the oldest inserted record is evicted so the store
    stays bounded under continuous debug-mode operation. Tests
    pin the default capacity at
    :data:`pi_platform.ports.retrieval.trace_store.DEFAULT_TRACE_STORE_LIMIT`
    so a regression in the bound is observable.
    """

    def __init__(self, *, capacity: int = DEFAULT_TRACE_STORE_LIMIT) -> None:
        if capacity <= 0:
            raise ValueError(
                f"InMemoryRetrievalTraceStore capacity must be positive, "
                f"got {capacity}"
            )
        self._capacity = capacity
        self._records: "OrderedDict[str, RetrievalTraceRecord]" = OrderedDict()
        self._lock = threading.Lock()
        self._evictions = 0
        self._stores = 0
        self._fetches = 0
        self._misses = 0

    def store(self, record: RetrievalTraceRecord) -> str:
        with self._lock:
            if record.trace_id in self._records:
                # Touch the record so the eviction order reflects
                # the most recent insertion when the same id is
                # stored twice.
                self._records.pop(record.trace_id, None)
                self._evictions += 1
            elif len(self._records) >= self._capacity:
                # FIFO eviction of the oldest record.
                self._records.popitem(last=False)
                self._evictions += 1
            self._records[record.trace_id] = record
            self._stores += 1
        return record.trace_id

    def fetch(self, trace_id: str) -> Optional[RetrievalTraceRecord]:
        with self._lock:
            self._fetches += 1
            record = self._records.get(trace_id)
            if record is None:
                self._misses += 1
                return None
            return record

    def list_ids(self) -> Sequence[str]:
        with self._lock:
            return tuple(self._records.keys())

    def evict(self, trace_id: str) -> bool:
        with self._lock:
            removed = self._records.pop(trace_id, None) is not None
            if removed:
                self._evictions += 1
            return removed

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "capacity": self._capacity,
                "stored": len(self._records),
                "stores": self._stores,
                "fetches": self._fetches,
                "misses": self._misses,
                "evictions": self._evictions,
            }

    @property
    def capacity(self) -> int:
        return self._capacity


def compute_trace_id(query_text: str, trace: RetrievalTrace) -> str:
    """Return a deterministic identifier for ``trace``.

    The id is the SHA-256 hex digest of a compact canonical encoding
    of the query text and the trace's :class:`RetrievalTrace`
    payload. Re-deriving the same trace twice (same query, same
    pipeline data) yields the same id, which lets the MCP server
    reconcile repeat debug-mode calls without leaking query text
    into the trace id itself.
    """

    import hashlib
    import json

    from dataclasses import asdict

    if not isinstance(query_text, str):
        query_text = str(query_text or "")
    try:
        encoded = json.dumps(asdict(trace), sort_keys=True,
                             separators=(",", ":"), default=str)
    except TypeError:
        encoded = repr(trace)
    digest = hashlib.sha256()
    digest.update(query_text.encode("utf-8"))
    digest.update(b"\x1f")
    digest.update(encoded.encode("utf-8"))
    return digest.hexdigest()
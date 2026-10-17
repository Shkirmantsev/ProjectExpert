"""Retrieval trace store port for the v0.8 refinement.

Change Package I of the v0.8 refinement
(``improve-ingestion-retrieval-local-models``) adds a debug-only
``project.get_retrieval_trace(trace_id)`` MCP tool. Plan §33 names
the retrieval-trace ID as part of the v0.8 surface; the MCP server
only returns the ID when the operator has enabled debug mode, and
the trace itself is held by a :class:`RetrievalTraceStorePort`.

The port is intentionally minimal so any backing store (in-memory
LRU, SQLite, audit-log file) can implement it. The default
implementation is :class:`InMemoryRetrievalTraceStore`; an SQLite
implementation can ship in a follow-up change that adds the
optional dependency group.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional, Sequence

from pi_platform.core.retrieval.retrieval_trace import RetrievalTrace


__all__ = [
    "DEFAULT_TRACE_STORE_LIMIT",
    "RetrievalTraceRecord",
    "RetrievalTraceStorePort",
]


# Default capacity of the in-memory trace store. The bound keeps
# the debug-only trace store from growing without limit when an
# operator leaves debug mode on for a long time; the oldest trace
# is evicted FIFO once the bound is exceeded.
DEFAULT_TRACE_STORE_LIMIT = 256


@dataclass(frozen=True)
class RetrievalTraceRecord:
    """A single trace record held by the store.

    ``trace_id`` is the deterministic identifier returned to MCP
    callers; ``query_text`` is the original query (used by debug
    tooling to correlate a trace with the originating tool call);
    ``trace`` is the frozen
    :class:`~pi_platform.core.retrieval.retrieval_trace.RetrievalTrace`
    value object produced by the multi-stage pipeline.
    """

    trace_id: str
    query_text: str
    trace: RetrievalTrace
    stored_at: str = ""


class RetrievalTraceStorePort(abc.ABC):
    """Abstract retrieval trace store port.

    Implementations MUST be safe to call from the asyncio event
    loop used by the MCP server. The default in-memory
    implementation uses a single :class:`threading.Lock`; SQLite
    implementations must serialise writes through a connection
    lock.
    """

    @abc.abstractmethod
    def store(
        self, record: RetrievalTraceRecord,
    ) -> str:
        """Persist ``record`` and return its ``trace_id``.

        Storing an existing ``trace_id`` MUST replace the prior
        record so the trace tool returns the most recent trace for
        the same identifier.
        """

    @abc.abstractmethod
    def fetch(
        self, trace_id: str,
    ) -> Optional[RetrievalTraceRecord]:
        """Return the record for ``trace_id`` or :data:`None`."""

    @abc.abstractmethod
    def list_ids(self) -> Sequence[str]:
        """Return the held trace IDs in FIFO insertion order."""

    @abc.abstractmethod
    def evict(self, trace_id: str) -> bool:
        """Remove the record for ``trace_id``.

        Returns :data:`True` when a record was removed, :data:`False`
        when the ID was not held.
        """

    @abc.abstractmethod
    def stats(self) -> dict[str, int]:
        """Return a small dict of counters for diagnostics panels."""
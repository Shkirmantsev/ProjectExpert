"""In-memory implementation of :class:`RuntimeCachePort`.

Used by the Phase 2 PipelineDriver and the Phase 2 regression tests
as a placeholder until Phase 3 ships the persistent
:class:`RuntimeStore`. The implementation is deterministic, process
local and thread safe.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional


__all__ = ["InMemoryRuntimeCache"]


class InMemoryRuntimeCache:
    """Phase 1 placeholder for the runtime content-addressed cache."""

    def __init__(self) -> None:
        self._store: Dict[str, bytes] = {}
        self._hit_count = 0
        self._miss_count = 0
        self._lock = threading.RLock()

    def get(self, content_hash: str) -> Optional[bytes]:
        with self._lock:
            if content_hash in self._store:
                self._hit_count += 1
                return self._store[content_hash]
            self._miss_count += 1
            return None

    def put(self, content_hash: str, payload: bytes) -> None:
        with self._lock:
            self._store[content_hash] = payload

    def hits(self) -> int:
        with self._lock:
            return self._hit_count

    def misses(self) -> int:
        with self._lock:
            return self._miss_count

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hit_count = 0
            self._miss_count = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

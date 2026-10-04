"""Process-local Phase 2 cache, source ownership, invalidation and stale provenance."""

import json
import threading
from dataclasses import replace
from pi_platform.core.canonical.value_types import (
    Chunk,
    ContextualChunk,
    Entity,
    Evidence,
    Relation,
    KnowledgeState,
    from_canonical_json,
    to_canonical_json,
)


class InMemoryRuntimeCache:
    def __init__(self):
        self._store = {}
        self._sources = {}
        self._owners = {}
        self._hit_count = 0
        self._miss_count = 0
        self._lock = threading.RLock()

    def get(self, key):
        with self._lock:
            if key in self._store:
                self._hit_count += 1
                return self._store[key]
            self._miss_count += 1
            return None

    def put(self, key, payload):
        with self._lock:
            self._store[key] = payload

    def delete(self, key):
        with self._lock:
            self._store.pop(key, None)

    def hits(self):
        return self._hit_count

    def misses(self):
        return self._miss_count

    def __len__(self):
        return len(self._store)

    def clear(self):
        with self._lock:
            self._store.clear()
            self._sources.clear()
            self._owners.clear()
            self._hit_count = 0
            self._miss_count = 0

    def source_is_current(self, sid, digest, metadata_key=None):
        with self._lock:
            record = self._sources.get(sid, {})
            return record.get("hash") == digest and (
                metadata_key is None or record.get("metadata_key") == metadata_key
            )

    def source_record(self, sid):
        with self._lock:
            return self._sources.get(sid)

    def complete_source(self, sid, digest, key, addresses, metadata_key=None):
        with self._lock:
            self._sources[sid] = {
                "hash": digest,
                "key": key,
                "addresses": tuple(addresses),
                "metadata_key": metadata_key,
            }
            for address in addresses:
                self._owners.setdefault(address, set()).add(sid)

    def invalidate_source(self, sid, *, stale=True):
        with self._lock:
            record = self._sources.pop(sid, None)
            if not record:
                return
            self._store.pop(record["key"], None)
            for key in record["addresses"]:
                owners = self._owners.get(key, set())
                owners.discard(sid)
                if owners:
                    continue
                self._owners.pop(key, None)
                if not stale:
                    self._store.pop(key, None)
                    continue
                raw = self._store.get(key)
                if raw is None:
                    continue
                data = json.loads(raw)
                if isinstance(data, dict):
                    if "provenance" in data:
                        data["provenance"]["knowledgeState"] = "stale"
                    if "knowledgeState" in data:
                        data["knowledgeState"] = "stale"
                    if "chunk" in data:
                        data["chunk"]["provenance"]["knowledgeState"] = "stale"
                    from pi_platform.core.canonical.serializer import (
                        canonical_dump_json,
                    )

                    self._store[key] = canonical_dump_json(data)

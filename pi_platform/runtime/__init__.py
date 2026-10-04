"""Runtime working knowledge stub.

Phase 1 ships a content-addressed filesystem cache. Phase 3 replaces
this with the embedded runtime store (relational + vector + graph).
"""

from .cache import RuntimeCache, RuntimeCacheError, CacheEntry

__all__ = ["RuntimeCache", "RuntimeCacheError", "CacheEntry"]
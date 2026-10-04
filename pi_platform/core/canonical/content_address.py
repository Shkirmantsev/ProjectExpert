"""SHA-256 content addressing for canonical artifacts.

Every canonical immutable object (parsed structure snapshot, normalized
chunk body, deterministic extracted relation, OKF concept page snapshot)
MUST be addressed by its SHA-256 hex digest of its deterministic
canonical serialization. This module is the single point that produces
such digests.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .serializer import canonical_dump_json

__all__ = [
    "content_address",
    "content_address_bytes",
    "content_address_for_canonical",
    "object_path",
]


def content_address_bytes(raw: bytes) -> str:
    """Return the SHA-256 hex digest of ``raw``."""

    return hashlib.sha256(raw).hexdigest()


def content_address(value: Any) -> str:
    """Return the SHA-256 hex digest of the canonical JSON encoding of
    ``value``.
    """

    return content_address_bytes(canonical_dump_json(value))


def content_address_for_canonical(value: Mapping[str, Any]) -> str:
    """Convenience wrapper for already-canonical mappings.

    Equivalent to :func:`content_address`; provided so callers can
    express intent without recomputing the canonical JSON document.
    """

    return content_address(value)


def object_path(content_hash: str) -> str:
    """Return the documented ``objects/<hash-prefix[0:2]>/<hash-rest>``
    filesystem path.
    """

    if len(content_hash) < 3:
        raise ValueError(
            "content_hash must be at least 3 hex characters for object "
            "sharding; got " + repr(content_hash)
        )
    prefix = content_hash[:2]
    rest = content_hash[2:]
    return f"objects/{prefix}/{rest}.json"
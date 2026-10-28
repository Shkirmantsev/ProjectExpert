"""Validated request limits and acquisition policy.

Every limit has a default and a hard maximum. A request above the hard
maximum is clamped to it and the *effective* limits are reported in the
result, so a caller always knows what was applied. A negative or
unbounded request is rejected outright: silently widening a request is
never acceptable.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from pi_platform.core.research.records import InvalidResearchRequest

__all__ = ["ResearchLimits", "AcquisitionPolicy"]


@dataclass(frozen=True)
class ResearchLimits:
    """Bounded limits for one research call."""

    max_nodes: int = 100
    max_depth: int = 5
    max_symbol_hits: int = 20
    max_code_lines: int = 200
    max_code_bytes: int = 16 * 1024
    timeout_seconds: float = 30.0

    # Hard maxima. These are properties of the service, not of the
    # request, so a caller can never raise the ceiling.
    HARD_MAX_NODES = 1000
    HARD_MAX_DEPTH = 20
    HARD_MAX_SYMBOL_HITS = 200
    HARD_MAX_CODE_LINES = 1000
    HARD_MAX_CODE_BYTES = 64 * 1024
    HARD_MAX_TIMEOUT_SECONDS = 120.0

    def __post_init__(self) -> None:
        for name in ("max_nodes", "max_depth", "max_symbol_hits",
                     "max_code_lines", "max_code_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidResearchRequest(f"{name} must be an integer")
            if value < 0:
                raise InvalidResearchRequest(f"{name} must not be negative")
        if self.max_nodes < 1:
            raise InvalidResearchRequest("max_nodes must be at least 1")
        timeout = self.timeout_seconds
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise InvalidResearchRequest("timeout_seconds must be a number")
        if timeout <= 0:
            raise InvalidResearchRequest("timeout_seconds must be positive")
        object.__setattr__(self, "max_nodes", min(self.max_nodes, self.HARD_MAX_NODES))
        object.__setattr__(self, "max_depth", min(self.max_depth, self.HARD_MAX_DEPTH))
        object.__setattr__(self, "max_symbol_hits",
                           min(self.max_symbol_hits, self.HARD_MAX_SYMBOL_HITS))
        object.__setattr__(self, "max_code_lines",
                           min(self.max_code_lines, self.HARD_MAX_CODE_LINES))
        object.__setattr__(self, "max_code_bytes",
                           min(self.max_code_bytes, self.HARD_MAX_CODE_BYTES))
        object.__setattr__(self, "timeout_seconds",
                           min(float(timeout), self.HARD_MAX_TIMEOUT_SECONDS))

    def as_dict(self) -> Mapping[str, Any]:
        return {
            "maxNodes": self.max_nodes,
            "maxDepth": self.max_depth,
            "maxSymbolHits": self.max_symbol_hits,
            "maxCodeLines": self.max_code_lines,
            "maxCodeBytes": self.max_code_bytes,
            "timeoutSeconds": self.timeout_seconds,
        }

    @property
    def fingerprint(self) -> str:
        """Stable identity of the effective limits.

        A cursor is bound to the limits it was produced under, so a
        later call with different limits cannot silently continue a
        truncated traversal.
        """

        return "|".join(
            f"{key}={value}" for key, value in sorted(self.as_dict().items())
        )


@dataclass(frozen=True)
class AcquisitionPolicy:
    """Policy for downloading a dependency artifact.

    Acquisition is an explicit, policy-controlled operation. It is
    never implicit in an inspection, and it never runs package code.
    """

    #: Approved registry identities, e.g. ``("pypi", "npm", "maven-central")``.
    allowed_sources: tuple[str, ...] = ()
    #: Hosts an approved source may serve or redirect to. An empty tuple
    #: means "no host restriction beyond https".
    allowed_hosts: tuple[str, ...] = ()
    max_compressed_bytes: int = 100 * 1024 * 1024
    max_expanded_bytes: int = 256 * 1024 * 1024
    max_members: int = 10_000
    max_compression_ratio: int = 200
    max_redirects: int = 3
    timeout_seconds: float = 120.0

    HARD_MAX_COMPRESSED_BYTES = 100 * 1024 * 1024
    HARD_MAX_EXPANDED_BYTES = 256 * 1024 * 1024
    HARD_MAX_MEMBERS = 10_000
    HARD_MAX_COMPRESSION_RATIO = 200
    HARD_MAX_REDIRECTS = 5
    HARD_MAX_TIMEOUT_SECONDS = 120.0

    def __post_init__(self) -> None:
        for name in ("max_compressed_bytes", "max_expanded_bytes",
                     "max_members", "max_compression_ratio", "max_redirects"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidResearchRequest(f"{name} must be an integer")
            if value < 1:
                raise InvalidResearchRequest(f"{name} must be positive")
        timeout = self.timeout_seconds
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise InvalidResearchRequest("timeout_seconds must be a number")
        if timeout <= 0:
            raise InvalidResearchRequest("timeout_seconds must be positive")
        object.__setattr__(self, "max_compressed_bytes",
                           min(self.max_compressed_bytes, self.HARD_MAX_COMPRESSED_BYTES))
        object.__setattr__(self, "max_expanded_bytes",
                           min(self.max_expanded_bytes, self.HARD_MAX_EXPANDED_BYTES))
        object.__setattr__(self, "max_members", min(self.max_members, self.HARD_MAX_MEMBERS))
        object.__setattr__(self, "max_compression_ratio",
                           min(self.max_compression_ratio, self.HARD_MAX_COMPRESSION_RATIO))
        object.__setattr__(self, "max_redirects",
                           min(self.max_redirects, self.HARD_MAX_REDIRECTS))
        object.__setattr__(self, "timeout_seconds",
                           min(float(timeout), self.HARD_MAX_TIMEOUT_SECONDS))

    def allows(self, source_id: str) -> bool:
        return source_id in self.allowed_sources

    def allows_host(self, host: str) -> bool:
        if not self.allowed_hosts:
            return True
        return host in self.allowed_hosts

    def as_dict(self) -> Mapping[str, Any]:
        return {
            "allowedSources": list(self.allowed_sources),
            "allowedHosts": list(self.allowed_hosts),
            "maxCompressedBytes": self.max_compressed_bytes,
            "maxExpandedBytes": self.max_expanded_bytes,
            "maxMembers": self.max_members,
            "maxCompressionRatio": self.max_compression_ratio,
            "maxRedirects": self.max_redirects,
            "timeoutSeconds": self.timeout_seconds,
        }

    @property
    def fingerprint(self) -> str:
        return "|".join(f"{key}={value}" for key, value in sorted(self.as_dict().items()))

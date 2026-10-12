"""Metadata filter port for the v0.8 Phase 4 retrieval layer.

Covers architecture sections §23 (Metadata as Correctness
Constraints), §24 (Temporal and Version-Aware Retrieval) and §56
(Enterprise Security Boundary). The :class:`MetadataFilterPort`
projects the documented temporal validity rule, the project-version
filter, the security-classification allow-list and the language /
domain / module / requirement filters the multi-stage retrieval
pipeline consumes.
"""

from __future__ import annotations

import abc
import datetime as _dt
from dataclasses import dataclass, field
from typing import Final, Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import ProjectVersion


__all__ = [
    "MetadataFilter",
    "MetadataFilterPort",
    "MetadataFilterError",
    "DropReason",
]


class MetadataFilterError(RuntimeError):
    """Raised when a metadata filter cannot be applied."""


# Drop reasons in the documented evaluation order. The
# :class:`MetadataFilterPort.apply` implementation MUST record one of
# these constants per dropped hit.
DROP_TEMPORAL_INVALID = "temporal_invalid"
DROP_VERSION_MISMATCH = "version_mismatch"
# Phase 4 baseline; preserved by Phase 8.
DROP_SECURITY_DENIED = "security_denied"
# Phase 8 additions for the Enterprise Security Boundary.
DROP_SECURITY_EGRESS_DENIED = "security_egress_denied"
DROP_SECURITY_REDACTED = "security_redacted"
DROP_LANGUAGE_MISMATCH = "language_mismatch"
DROP_DOMAIN_MISMATCH = "domain_mismatch"
DROP_MODULE_MISMATCH = "module_mismatch"
DROP_REQUIREMENT_MISMATCH = "requirement_mismatch"
DROP_REASON_ORDER: Final = (
    DROP_TEMPORAL_INVALID,
    DROP_VERSION_MISMATCH,
    DROP_SECURITY_DENIED,
    DROP_SECURITY_EGRESS_DENIED,
    DROP_SECURITY_REDACTED,
    DROP_LANGUAGE_MISMATCH,
    DROP_DOMAIN_MISMATCH,
    DROP_MODULE_MISMATCH,
    DROP_REQUIREMENT_MISMATCH,
)


@dataclass(frozen=True)
class DropReason:
    """Structured reason a hit was filtered out.

    Encoded as a string constant from :data:`DROP_REASON_ORDER` plus
    the hit's :class:`pi_platform.ports.retrieval.hybrid_retrieval.RetrievalHit`
    identifier so the multi-stage pipeline can report per-reason
    counts.
    """

    reason: str
    chunkId: str

    def __post_init__(self) -> None:
        if self.reason not in DROP_REASON_ORDER:
            raise ValueError(
                f"DropReason.reason must be one of {DROP_REASON_ORDER}, "
                f"got {self.reason!r}"
            )


@dataclass(frozen=True)
class MetadataFilter:
    """§24 temporal / version / security filter projection.

    Phase 8 adds the role-aware ``actor_role`` field so the
    wired Enterprise Boundary can run source-permission
    checks for the correct caller. ``actor_capabilities``
    carries the caller's granted capability set (per the
    §59.4 vocabulary) so the boundary can enforce
    capability-based delegation. Both default to
    ``Role.VIEWER`` and an empty tuple to preserve the
    Phase 4 baseline behaviour for callers that do not
    thread role / capability information.
    """

    queryDate: Optional[_dt.date] = None
    projectVersion: Optional[ProjectVersion] = None
    languages: Optional[Sequence[str]] = None
    businessDomains: Optional[Sequence[str]] = None
    modules: Optional[Sequence[str]] = None
    requirementIds: Optional[Sequence[str]] = None
    securityClassifications: Optional[Sequence[str]] = None
    # Phase 8 additions — frozen dataclass field defaults
    # must be at the end of the positional list and the
    # field types must be importable lazily.
    actor_role: object = field(default=None, repr=False)
    actor_capabilities: tuple = field(default=(), repr=False)

    def issues(self) -> Sequence[str]:
        """Return validation issues (empty list when well-formed)."""

        problems: list[str] = []
        if self.queryDate is not None and not isinstance(
            self.queryDate, _dt.date,
        ):
            problems.append("queryDate must be a datetime.date instance")
        if self.languages is not None and not all(
            isinstance(s, str) for s in self.languages
        ):
            problems.append("languages must be a sequence of strings")
        if self.securityClassifications is not None and not all(
            isinstance(s, str) for s in self.securityClassifications
        ):
            problems.append(
                "securityClassifications must be a sequence of strings"
            )
        if self.actor_capabilities and not all(
            isinstance(s, str) for s in self.actor_capabilities
        ):
            problems.append(
                "actor_capabilities must be a tuple of strings"
            )
        return tuple(problems)

    def with_actor(self, *, actor_role, actor_capabilities=()) -> "MetadataFilter":
        """Return a copy with the actor fields populated.

        Used by the multi-stage retrieval pipeline to thread
        the calling actor's role and granted capabilities
        through the Phase 8 Enterprise Boundary without
        breaking the Phase 4 frozen-dataclass contract.
        """

        return MetadataFilter(
            queryDate=self.queryDate,
            projectVersion=self.projectVersion,
            languages=self.languages,
            businessDomains=self.businessDomains,
            modules=self.modules,
            requirementIds=self.requirementIds,
            securityClassifications=self.securityClassifications,
            actor_role=actor_role,
            actor_capabilities=tuple(actor_capabilities or ()),
        )


class MetadataFilterPort(abc.ABC):
    """Abstract metadata filter port."""

    @abc.abstractmethod
    def apply(
        self, filter: MetadataFilter, hits: Sequence[object],
    ) -> Sequence[object]: ...

    @abc.abstractmethod
    def validate(self, filter: MetadataFilter) -> Sequence[str]: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...


# Imported lazily so the port module stays free of imports outside
# its own scope at import time. Used by the core implementation.
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit  # noqa: E402,F401
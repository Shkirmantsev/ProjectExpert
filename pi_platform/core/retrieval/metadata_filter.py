"""Default metadata filter core.

Implements :class:`pi_platform.ports.retrieval.metadata_filter.MetadataFilterPort`
with the documented evaluation order:

1. ``temporal_invalid`` — drops chunks whose
   ``validFrom <= queryDate AND (validTo IS NULL OR validTo >=
   queryDate)`` rule is violated;
2. ``version_mismatch`` — drops chunks whose Git / project version
   differs from the bound ``MetadataFilter.projectVersion``;
3. ``security_denied`` — drops chunks whose security classification
   is not in the allow-list;
4. ``language_mismatch``, ``domain_mismatch``, ``module_mismatch``
   and ``requirement_mismatch`` — drop chunks whose language /
   domain / module / requirement identifiers do not match the
   configured filter lists.

Hits whose metadata lacks a temporal validity field are always kept
(scenario: ``temporal validity keeps open-ended hits``). Hits
without a ``securityClassification`` field are treated as
``PUBLIC`` so a missing field never silently leaks ``RESTRICTED``
content.
"""

from __future__ import annotations

import datetime as _dt
from typing import Mapping, Sequence

from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.metadata_filter import (
    DROP_DOMAIN_MISMATCH,
    DROP_LANGUAGE_MISMATCH,
    DROP_MODULE_MISMATCH,
    DROP_REQUIREMENT_MISMATCH,
    DROP_SECURITY_DENIED,
    DROP_TEMPORAL_INVALID,
    DROP_VERSION_MISMATCH,
    MetadataFilter,
    MetadataFilterError,
    MetadataFilterPort,
)


__all__ = [
    "MetadataFilterCore",
    "DEFAULT_SECURITY_PUBLIC",
]


DEFAULT_SECURITY_PUBLIC = "PUBLIC"


def _parse_iso_date(value: str | None) -> _dt.date | None:
    if not value:
        return None
    try:
        return _dt.datetime.fromisoformat(value).date()
    except ValueError:
        return None


class MetadataFilterCore(MetadataFilterPort):
    """Default §24 / §56 metadata filter projection."""

    def __init__(
        self, *, default_security: str = DEFAULT_SECURITY_PUBLIC,
    ) -> None:
        self._default_security = default_security
        self._calls = 0
        self._dropped = 0
        self._dropped_by_reason: dict[str, int] = {}

    def apply(
        self, filter: MetadataFilter, hits: Sequence[RetrievalHit],
    ) -> Sequence[RetrievalHit]:
        self._calls += 1
        kept: list[RetrievalHit] = []
        for hit in hits:
            reason = self._drop_reason(filter, hit)
            if reason is None:
                kept.append(hit)
                continue
            self._dropped += 1
            self._dropped_by_reason[reason] = (
                self._dropped_by_reason.get(reason, 0) + 1
            )
        return tuple(kept)

    def validate(self, filter: MetadataFilter) -> Sequence[str]:
        return tuple(filter.issues())

    def stats(self) -> Mapping[str, int]:
        base = {"calls": self._calls, "dropped": self._dropped}
        base.update(self._dropped_by_reason)
        return base

    # -- internal helpers --------------------------------------------------

    def _drop_reason(
        self, filter: MetadataFilter, hit: RetrievalHit,
    ) -> str | None:
        temporal = self._temporal_violated(filter, hit)
        if temporal:
            return "temporal_invalid"
        if filter.projectVersion is not None:
            md = hit.metadata
            if (
                md.gitCommit
                and md.gitCommit != filter.projectVersion.gitHead
            ):
                return "version_mismatch"
        if filter.securityClassifications is not None:
            cls = (
                hit.metadata.securityClassification
                or self._default_security
            )
            if cls not in filter.securityClassifications:
                return "security_denied"
        if filter.languages is not None and hit.metadata.language:
            if hit.metadata.language not in filter.languages:
                return "language_mismatch"
        if filter.businessDomains is not None and hit.metadata.businessDomain:
            if hit.metadata.businessDomain not in filter.businessDomains:
                return "domain_mismatch"
        if filter.modules is not None and hit.metadata.module:
            if hit.metadata.module not in filter.modules:
                return "module_mismatch"
        if filter.requirementIds is not None and hit.metadata.requirementId:
            if hit.metadata.requirementId not in filter.requirementIds:
                return "requirement_mismatch"
        return None

    def _temporal_violated(
        self, filter: MetadataFilter, hit: RetrievalHit,
    ) -> bool:
        if filter.queryDate is None:
            return False
        valid_from = _parse_iso_date(hit.metadata.validFrom)
        valid_to = _parse_iso_date(hit.metadata.validTo)
        if valid_from is None and valid_to is None:
            return False
        if valid_from is not None and valid_from > filter.queryDate:
            return True
        if valid_to is not None and valid_to < filter.queryDate:
            return True
        return False


# Re-export the drop-reason constants for convenience.
__all__ += [
    "DROP_TEMPORAL_INVALID",
    "DROP_VERSION_MISMATCH",
    "DROP_SECURITY_DENIED",
    "DROP_LANGUAGE_MISMATCH",
    "DROP_DOMAIN_MISMATCH",
    "DROP_MODULE_MISMATCH",
    "DROP_REQUIREMENT_MISMATCH",
]  # type: ignore[misc]
"""Default metadata filter core.

Implements :class:`pi_platform.ports.retrieval.metadata_filter.MetadataFilterPort`
with the documented evaluation order:

1. ``temporal_invalid`` — drops chunks whose
   ``validFrom <= queryDate AND (validTo IS NULL OR validTo >=
   queryDate)`` rule is violated;
2. ``version_mismatch`` — drops chunks whose Git / project version
   differs from the bound ``MetadataFilter.projectVersion``;
3. ``security_denied`` — drops chunks whose security classification
   is not in the allow-list. This Phase 4 reason is preserved by
   Phase 8 even when a boundary is wired.
4. ``security_egress_denied`` (Phase 8) — drops chunks when the
   Enterprise Boundary denies the candidate because the consumer
   role cannot reach the source classification AND the chunk is
   bound for an egress-bound consumer.
5. ``security_redacted`` (Phase 8) — *keeps* the chunk but records
   this reason in the dropped-by-reason shadow counter; the
   context assembler replaces the textual content with
   ``[REDACTED:<LEVEL>]`` before serialisation.
6. ``language_mismatch``, ``domain_mismatch``, ``module_mismatch``
   and ``requirement_mismatch`` — drop chunks whose language /
   domain / module / requirement identifiers do not match the
   configured filter lists.

Hits whose metadata lacks a temporal validity field are always kept
(scenario: ``temporal validity keeps open-ended hits``). Hits
without a ``securityClassification`` field are treated as
``PUBLIC`` so a missing field never silently leaks ``RESTRICTED``
content.

Phase 8 Enterprise Boundary integration: when the filter is
constructed with ``enterprise_boundary=...`` the boundary
participates in the security evaluation (steps 4-5). A
``MetadataFilterCore`` constructed without ``enterprise_boundary``
behaves identically to the Phase 4 baseline.

The filter also exposes a redacted-hit counter via
:attr:`redacted_count` so the multi-stage pipeline can adapt
downstream (e.g. the context assembler reads it to decide how
many of the kept hits need their text replaced with
``[REDACTED:<LEVEL>]``).
"""

from __future__ import annotations

import datetime as _dt
from typing import Mapping, Optional, Sequence

from pi_platform.ports.control.policy import Role
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.metadata_filter import (
    DROP_DOMAIN_MISMATCH,
    DROP_LANGUAGE_MISMATCH,
    DROP_MODULE_MISMATCH,
    DROP_REQUIREMENT_MISMATCH,
    DROP_SECURITY_DENIED,
    DROP_SECURITY_EGRESS_DENIED,
    DROP_SECURITY_REDACTED,
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
    """Default §24 / §56 / §68 metadata filter projection."""

    def __init__(
        self, *, default_security: str = DEFAULT_SECURITY_PUBLIC,
        enterprise_boundary=None,
    ) -> None:
        # ``enterprise_boundary`` is an optional
        # :class:`pi_platform.ports.security.boundary.EnterpriseBoundaryPort`.
        # The import is deferred to keep module-load ordering
        # independent of the security package.
        self._default_security = default_security
        self._enterprise_boundary = enterprise_boundary
        self._calls = 0
        self._dropped = 0
        # ``_redacted`` tracks kept-but-redacted hits so the
        # :attr:`redacted_count` can be reported alongside
        # the dropped reasons.
        self._redacted = 0
        self._dropped_by_reason: dict[str, int] = {}

    @property
    def redacted_count(self) -> int:
        return self._redacted

    def apply(
        self, filter: MetadataFilter, hits: Sequence[RetrievalHit],
    ) -> Sequence[RetrievalHit]:
        self._calls += 1
        kept: list[RetrievalHit] = []
        for hit in hits:
            outcome = self._decide(filter, hit)
            if outcome is None:
                kept.append(hit)
                continue
            kind, redacted = outcome
            if redacted:
                # Redacted hits are KEPT (not dropped) but
                # their textual content is replaced with the
                # documented ``[REDACTED:<LEVEL>]`` marker
                # at the filter boundary. This is the
                # single point at which classification-driven
                # redaction is applied to the retrieval
                # path; downstream consumers see the
                # redacted text and never the raw chunk.
                kept.append(self._redact_hit(hit))
                self._redacted += 1
                self._dropped_by_reason[kind] = (
                    self._dropped_by_reason.get(kind, 0) + 1
                )
                continue
            self._dropped += 1
            self._dropped_by_reason[kind] = (
                self._dropped_by_reason.get(kind, 0) + 1
            )
        return tuple(kept)

    def validate(self, filter: MetadataFilter) -> Sequence[str]:
        return tuple(filter.issues())

    def stats(self) -> Mapping[str, int]:
        base = {
            "calls": self._calls, "dropped": self._dropped,
            "redacted": self._redacted,
        }
        base.update(self._dropped_by_reason)
        return base

    # -- internal helpers --------------------------------------------------

    def _decide(
        self, filter: MetadataFilter, hit: RetrievalHit,
    ) -> Optional[tuple]:
        """Return ``None`` when the hit is kept; otherwise a
        ``(reason, redacted)`` tuple. ``redacted=True`` means
        the hit is kept and only its textual content needs
        replacement; ``redacted=False`` means the hit is
        dropped from the candidate set.
        """

        if self._temporal_violated(filter, hit):
            return (DROP_TEMPORAL_INVALID, False)
        if filter.projectVersion is not None:
            md = hit.metadata
            if (
                md.gitCommit
                and md.gitCommit != filter.projectVersion.gitHead
            ):
                return (DROP_VERSION_MISMATCH, False)
        # Phase 4 baseline FIRST so the historical reason is
        # preserved. The allow-list is a hard drop; the
        # boundary consults the source-permission port and
        # the egress port for finer-grained rules.
        if filter.securityClassifications is not None:
            cls = (
                hit.metadata.securityClassification
                or self._default_security
            )
            if cls not in filter.securityClassifications:
                return (DROP_SECURITY_DENIED, False)
        # Phase 8: the boundary is consulted only AFTER the
        # allow-list has passed, so a mislabelled RESTRICTED
        # chunk reaching a viewer surfaces the Phase 4
        # reason first. The boundary then refines with
        # source-permission REDACT / DENY.
        boundary_decision = self._boundary_decision(filter, hit)
        if boundary_decision is not None:
            return boundary_decision
        if filter.languages is not None and hit.metadata.language:
            if hit.metadata.language not in filter.languages:
                return (DROP_LANGUAGE_MISMATCH, False)
        if filter.businessDomains is not None and hit.metadata.businessDomain:
            if hit.metadata.businessDomain not in filter.businessDomains:
                return (DROP_DOMAIN_MISMATCH, False)
        if filter.modules is not None and hit.metadata.module:
            if hit.metadata.module not in filter.modules:
                return (DROP_MODULE_MISMATCH, False)
        if filter.requirementIds is not None and hit.metadata.requirementId:
            if hit.metadata.requirementId not in filter.requirementIds:
                return (DROP_REQUIREMENT_MISMATCH, False)
        return None

    def _boundary_decision(
        self, filter: MetadataFilter, hit: RetrievalHit,
    ) -> Optional[tuple]:
        """Return ``(reason, redacted)`` when the wired
        boundary modifies the decision; ``None`` when no
        boundary is wired or when the boundary silently
        passes the candidate to the language / domain
        filters.
        """

        boundary = self._enterprise_boundary
        if boundary is None:
            return None
        from pi_platform.ports.security.permission import (
            SourcePermissionDecisionKind,
        )
        actor_role = filter.actor_role or Role.VIEWER
        actor_capabilities = tuple(
            getattr(filter, "actor_capabilities", ()) or ()
        )
        classification = (
            hit.metadata.securityClassification
            or self._default_security
        )
        source_id = (
            getattr(hit.metadata, "sourceId", "") or ""
        )
        try:
            decision = boundary.source_permission(
                source_id=source_id,
                classification=classification,
                actor_role=actor_role,
                actor_capabilities=actor_capabilities,
            )
        except Exception:
            # Boundary failure MUST NOT silently widen
            # access. The filter is the security boundary;
            # a broken boundary must fail closed.
            return (DROP_SECURITY_DENIED, False)
        # Phase 8: source-permission REDACT keeps the hit;
        # source-permission DENY drops it under the
        # ``security_egress_denied`` reason. The egress port
        # itself is consulted from the boundary composition
        # root at materialisation time, so the filter's
        # reason is the source-permission verdict, not the
        # egress verdict.
        if decision.decision is SourcePermissionDecisionKind.DENY:
            return (DROP_SECURITY_EGRESS_DENIED, False)
        if decision.decision is SourcePermissionDecisionKind.REDACT:
            return (DROP_SECURITY_REDACTED, True)
        return None

    def _redact_hit(self, hit: RetrievalHit) -> RetrievalHit:
        """Return a copy of ``hit`` whose ``snippet`` and
        ``contentHash`` carry the documented
        ``[REDACTED:<LEVEL>]`` marker so downstream
        consumers see only the redacted form. The original
        hit is not mutated (RetrievalHit is frozen).
        """

        from pi_platform.ports.security.classification import coerce_level
        level = coerce_level(
            hit.metadata.securityClassification,
        )
        marker = f"[REDACTED:{level.value}]"
        return RetrievalHit(
            chunkId=hit.chunkId,
            score=hit.score,
            source=hit.source,
            snippet=marker,
            contentHash=hit.contentHash,
            metadata=hit.metadata,
            knowledgeState=hit.knowledgeState,
            tokenEstimate=hit.tokenEstimate,
            dropReason=DROP_SECURITY_REDACTED,
            evidenceWeight=hit.evidenceWeight,
        )

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
    "DROP_SECURITY_EGRESS_DENIED",
    "DROP_SECURITY_REDACTED",
    "DROP_LANGUAGE_MISMATCH",
    "DROP_DOMAIN_MISMATCH",
    "DROP_MODULE_MISMATCH",
    "DROP_REQUIREMENT_MISMATCH",
]  # type: ignore[misc]

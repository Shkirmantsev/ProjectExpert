"""Phase 8 §56 default Source-Level Permission policy.

Default policy (per the capability spec):

- (source, PUBLIC)                           -> ALLOW
- (source, INTERNAL)                         -> ALLOW when role
  is not ``CODING_AGENT_READ_ONLY`` else REDACT
- (source, CONFIDENTIAL)                     -> REDACT for
  ``VIEWER`` / ``CODING_AGENT_READ_ONLY``,
  ALLOW for ``MAINTAINER`` / ``ADMINISTRATOR``
- (source, RESTRICTED)                       -> DENY unless role
  is ``ADMINISTRATOR``

The source ceiling is treated as a max-bound: a chunk whose
classification exceeds the configured source ceiling is
clamped down to the ceiling, but a chunk whose
classification is below the source ceiling is left alone.
A source with the default PUBLIC ceiling does not clamp
non-PUBLIC chunks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from pi_platform.ports.control.policy import Role
from pi_platform.ports.security.classification import coerce_level
from pi_platform.ports.security.classification import DEFAULT_LEVEL
from pi_platform.ports.security.classification import RANK
from pi_platform.ports.security.permission import (
    SourcePermissionDecision,
    SourcePermissionDecisionKind,
    SourcePermissionPort,
)


__all__ = ["DefaultSourcePermissionPolicy"]


_PRIVILEGED = (Role.MAINTAINER, Role.ADMINISTRATOR)
_RESTRICTED_READERS = (Role.VIEWER, Role.CODING_AGENT_READ_ONLY)


def _rank_to_level(rank: int) -> str:
    return (
        DEFAULT_LEVEL.value if rank == 0
        else "INTERNAL" if rank == 1
        else "CONFIDENTIAL" if rank == 2
        else "RESTRICTED"
    )


@dataclass
class DefaultSourcePermissionPolicy(SourcePermissionPort):
    """§56 default source-permission policy."""

    _ceilings: Dict[str, str] = field(default_factory=dict)

    def ceiling_for(self, source_id: str) -> str:
        return self._ceilings.get(source_id, DEFAULT_LEVEL.value)

    def set_ceiling(self, source_id: str, level: str) -> None:
        normalised = coerce_level(level).value
        self._ceilings[source_id] = normalised

    def _effective_level(
        self, source_id: str, classification: str,
    ) -> str:
        """Return the effective classification after
        clamping by the source ceiling.

        The source ceiling is a *max-bound*: a chunk
        whose classification exceeds the configured
        ceiling is clamped down to the ceiling. A source
        with the default PUBLIC ceiling is treated as
        "no explicit ceiling" and never clamps a
        non-PUBLIC chunk down to PUBLIC — the trust
        default is to honour the chunk's own
        classification.
        """

        chunk_level = coerce_level(classification)
        ceiling = self.ceiling_for(source_id)
        chunk_rank = RANK[chunk_level]
        ceiling_rank = RANK[coerce_level(ceiling)]
        if source_id not in self._ceilings:
            # No explicit ceiling; trust the chunk.
            effective_rank = chunk_rank
        else:
            effective_rank = min(chunk_rank, ceiling_rank)
        return _rank_to_level(effective_rank)

    def evaluate(
        self, *, source_id: str, classification: str,
        actor_role: Role, actor_capabilities: tuple = (),
    ) -> SourcePermissionDecision:
        # Capability delegation: actors without
        # ``secret.reference`` MUST be denied access to
        # any payload whose classification is ``>= INTERNAL``.
        capabilities = set(actor_capabilities or ())
        level_value = self._effective_level(source_id, classification)
        if (
            level_value != DEFAULT_LEVEL.value
            and "secret.reference" not in capabilities
        ):
            return SourcePermissionDecision(
                decision=SourcePermissionDecisionKind.DENY,
                classification=level_value,
                rule="missing_secret_reference",
                rationale=(
                    "actor without secret.reference cannot access "
                    f"{level_value} content"
                ),
            )

        if level_value == DEFAULT_LEVEL.value:
            return SourcePermissionDecision(
                decision=SourcePermissionDecisionKind.ALLOW,
                classification=level_value,
                rule="public_allow",
                rationale="public content is always allowed",
            )

        if level_value == "INTERNAL":
            if actor_role is Role.CODING_AGENT_READ_ONLY:
                return SourcePermissionDecision(
                    decision=SourcePermissionDecisionKind.REDACT,
                    classification=level_value,
                    rule="coding_agent_internal",
                    rationale="coding-agent-read-only consumer "
                    "cannot view INTERNAL content",
                )
            return SourcePermissionDecision(
                decision=SourcePermissionDecisionKind.ALLOW,
                classification=level_value,
                rule="internal_allow",
                rationale="internal content allowed for non-"
                "coding-agent consumers",
            )

        if level_value == "CONFIDENTIAL":
            if actor_role in _RESTRICTED_READERS:
                return SourcePermissionDecision(
                    decision=SourcePermissionDecisionKind.REDACT,
                    classification=level_value,
                    rule="confidential_restricted_reader",
                    rationale="confidential content redacted for "
                    "viewer / coding-agent-read-only",
                )
            if actor_role in _PRIVILEGED:
                return SourcePermissionDecision(
                    decision=SourcePermissionDecisionKind.ALLOW,
                    classification=level_value,
                    rule="maintainer_confidential",
                    rationale="maintainer / administrator may view "
                    "confidential content",
                )
            return SourcePermissionDecision(
                decision=SourcePermissionDecisionKind.REDACT,
                classification=level_value,
                rule="confidential_default",
                rationale="confidential content redacted by default",
            )

        # RESTRICTED
        if actor_role is Role.ADMINISTRATOR:
            return SourcePermissionDecision(
                decision=SourcePermissionDecisionKind.ALLOW,
                classification=level_value,
                rule="admin_restricted",
                rationale="administrator may view restricted content",
            )
        return SourcePermissionDecision(
            decision=SourcePermissionDecisionKind.DENY,
            classification=level_value,
            rule="restricted_deny",
            rationale="restricted content denied to non-admin "
            "actors",
        )

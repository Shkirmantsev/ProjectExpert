"""Phase 7 §59.4, §59.5, §59.11, §59.12 policy engine port.

The policy engine is the central authorisation source for
every sensitive execution path (MCP tool, A2A request, REST
request, plugin, hook, agent delegation, materialisation,
Git write, secret resolution, external network request).

The vocabulary is shared across UI users, coding agents,
A2A agents, plugins, hooks, CLI operations and automation.

The engine returns one of three decisions:

* ``ALLOW`` — the request is authorised;
* ``DENY`` — the request is rejected;
* ``REQUIRE_APPROVAL`` — the request is authorised only
  after a typed approval token is presented to the calling
  subsystem.

The Phase 1 ``PolicyDecisionStub`` continues to back the
Phase 1 ``MaterialiseService`` until the Phase 7
implementation rewires it; this port never bypasses the
Phase 1 ``TrustedApprovalBoundary``.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional


__all__ = [
    "ApprovalRequired",
    "Capability",
    "Decision",
    "DeniedError",
    "PolicyDecision",
    "PolicyEnginePort",
    "PolicyRequest",
    "Role",
    "UnknownCapabilityError",
    "DEFAULT_ROLE_CAPABILITIES",
    "ROLE_VIEWER",
    "ROLE_DEVELOPER",
    "ROLE_MAINTAINER",
    "ROLE_ADMINISTRATOR",
    "ROLE_CODING_AGENT_READ_ONLY",
]


class Capability(str, enum.Enum):
    """§59.4 capability vocabulary.

    The enumeration values are the canonical string
    identifiers used by every control-plane subsystem. A
    subsystem that requests a value outside the
    enumeration MUST be rejected with
    :class:`UnknownCapabilityError`.
    """

    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_WRITE = "knowledge.write"
    KNOWLEDGE_MATERIALIZE = "knowledge.materialize"

    RETRIEVAL_QUERY = "retrieval.query"
    RETRIEVAL_ADMIN = "retrieval.admin"

    GRAPH_READ = "graph.read"
    GRAPH_WRITE = "graph.write"

    SOURCE_READ = "source.read"
    SOURCE_IMPORT = "source.import"

    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"

    GIT_READ = "git.read"
    GIT_WRITE = "git.write"

    CONFIG_READ = "config.read"
    CONFIG_WRITE = "config.write"

    SECRET_REFERENCE = "secret.reference"
    SECRET_RESOLVE = "secret.resolve"

    MCP_INVOKE = "mcp.invoke"
    MCP_ADMIN = "mcp.admin"

    AGENT_DELEGATE = "agent.delegate"

    NETWORK_LOCAL = "network.local"
    NETWORK_EXTERNAL = "network.external"

    AUDIT_READ = "audit.read"
    AUDIT_WRITE = "audit.write"


class Role(str, enum.Enum):
    """§59.5 role defaults.

    Role defaults are convenience initialisers; the
    authorisation source of truth is the capability
    vocabulary.
    """

    VIEWER = "viewer"
    DEVELOPER = "developer"
    MAINTAINER = "maintainer"
    ADMINISTRATOR = "administrator"
    CODING_AGENT_READ_ONLY = "coding_agent_read_only"


# ---------------------------------------------------------------------------
# Role defaults (the documented §59.5 capability assignment)
# ---------------------------------------------------------------------------

ROLE_VIEWER: tuple[Capability, ...] = (
    Capability.KNOWLEDGE_READ,
    Capability.RETRIEVAL_QUERY,
    Capability.GRAPH_READ,
    Capability.SOURCE_READ,
    Capability.GIT_READ,
    Capability.CONFIG_READ,
    Capability.AUDIT_READ,
)

ROLE_DEVELOPER: tuple[Capability, ...] = (
    *ROLE_VIEWER,
    Capability.FILESYSTEM_WRITE,
    Capability.CONFIG_WRITE,
    Capability.SOURCE_IMPORT,
    Capability.MCP_INVOKE,
    Capability.AUDIT_WRITE,
)

ROLE_MAINTAINER: tuple[Capability, ...] = (
    *ROLE_DEVELOPER,
    Capability.KNOWLEDGE_WRITE,
    Capability.GRAPH_WRITE,
    Capability.RETRIEVAL_ADMIN,
    Capability.GIT_WRITE,
    Capability.SECRET_REFERENCE,
    Capability.MCP_ADMIN,
    Capability.AGENT_DELEGATE,
    Capability.NETWORK_LOCAL,
)

ROLE_ADMINISTRATOR: tuple[Capability, ...] = (
    *ROLE_MAINTAINER,
    Capability.KNOWLEDGE_MATERIALIZE,
    Capability.SECRET_RESOLVE,
    Capability.NETWORK_EXTERNAL,
)

# §59.8 read-only coding agent capability set
ROLE_CODING_AGENT_READ_ONLY: tuple[Capability, ...] = (
    Capability.KNOWLEDGE_READ,
    Capability.RETRIEVAL_QUERY,
    Capability.CONFIG_READ,
    Capability.AUDIT_WRITE,
)


DEFAULT_ROLE_CAPABILITIES: Mapping[Role, tuple[Capability, ...]] = {
    Role.VIEWER: ROLE_VIEWER,
    Role.DEVELOPER: ROLE_DEVELOPER,
    Role.MAINTAINER: ROLE_MAINTAINER,
    Role.ADMINISTRATOR: ROLE_ADMINISTRATOR,
    Role.CODING_AGENT_READ_ONLY: ROLE_CODING_AGENT_READ_ONLY,
}


# ---------------------------------------------------------------------------
# Decision contract
# ---------------------------------------------------------------------------


class Decision(str, enum.Enum):
    """§59.11 decision contract."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


@dataclass(frozen=True)
class PolicyRequest:
    """The actor + role + capability + resource + project/version
    request that the policy engine evaluates.

    Attributes:
        actor_type: ``"user"``, ``"agent"``, ``"plugin"``,
            ``"hook"`` or ``"automation"``.
        actor_id: stable identifier for the calling actor.
        role: the role default the actor carries; the
            engine resolves the role to a capability set
            and then evaluates the requested capability.
        capability: the capability the actor requests.
        resource: opaque resource identifier (plugin id,
            secret reference, MCP tool name, etc.).
        project_version: the canonical project / version
            context for branch / version filtering.
        correlation_id: deterministic correlation id; used
            to chain policy, audit and hook records.
        approval_token: optional approval token for
            high-impact actions; when present the engine
            re-evaluates ``REQUIRE_APPROVAL`` requests.
    """

    actor_type: str
    actor_id: str
    role: Role
    capability: Capability
    resource: str
    project_version: str
    correlation_id: str
    approval_token: Optional[str] = None


@dataclass(frozen=True)
class PolicyDecision:
    """The typed result of a policy evaluation."""

    decision: Decision
    capability: Capability
    resource: str
    policy_decision_rationale: str = ""
    approval_request_id: Optional[str] = None

    def is_authorised(self) -> bool:
        return self.decision is Decision.ALLOW


class DeniedError(RuntimeError):
    """Raised when the policy engine returns ``DENY``."""


class ApprovalRequired(RuntimeError):
    """Raised when the policy engine returns
    ``REQUIRE_APPROVAL`` and the caller did not supply a
    valid ``approval_token``.

    The Phase 1 ``MaterialiseService`` translates this
    error into its documented approval contract; the Phase 6
    MCP server translates it into the §49 typed error
    payload.
    """

    def __init__(self, *, capability: Capability, resource: str,
                 approval_request_id: Optional[str],
                 rationale: str) -> None:
        self.capability = capability
        self.resource = resource
        self.approval_request_id = approval_request_id
        self.rationale = rationale
        super().__init__(
            f"approval-required: capability={capability.value} "
            f"resource={resource!r} approval_request_id="
            f"{approval_request_id!r}; {rationale}"
        )


class UnknownCapabilityError(RuntimeError):
    """Raised when an actor requests a capability outside the
    documented §59.4 vocabulary.
    """


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------


class PolicyEnginePort(abc.ABC):
    """§59.11 central policy engine port."""

    @abc.abstractmethod
    def evaluate(self, request: PolicyRequest) -> PolicyDecision: ...

    @abc.abstractmethod
    def authorize(self, request: PolicyRequest) -> None:
        """Raise :class:`DeniedError` or
        :class:`ApprovalRequired` when the decision is not
        ``ALLOW``. Returns ``None`` when authorised.
        """

    @abc.abstractmethod
    def capabilities_for(self, role: Role) -> tuple[Capability, ...]: ...

    @abc.abstractmethod
    def override(self, actor_id: str,
                 capabilities: Iterable[Capability]) -> None: ...

    @abc.abstractmethod
    def serialise(self) -> str:
        """Byte-stable JSON serialisation for two consecutive
        reads.
        """
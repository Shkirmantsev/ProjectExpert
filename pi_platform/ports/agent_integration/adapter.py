"""Phase 6 §40 + §46 agent-integration adapter port.

Every vendor-specific adapter (Codex, Claude Code, OpenCode,
generic agent) implements the documented 8-operation contract.
The contract is intentionally narrow: install, configure MCP,
install the canonical Agent Skill, verify compatibility, run a
health check, uninstall, and describe. Adapters MUST NOT own
retrieval or business rules; they only manipulate owned
configuration files in isolated target projects.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence


__all__ = [
    "AdapterError",
    "AdapterHealthReport",
    "AdapterInstallResult",
    "AgentIntegrationAdapter",
    "AgentIntegrationError",
    "CapabilityMismatchError",
    "InstallRefusedError",
    "UnsupportedClientError",
    "VendorProfile",
]


class AgentIntegrationError(RuntimeError):
    """Base typed error for the adapter contract."""


class UnsupportedClientError(AgentIntegrationError):
    """Raised when the adapter does not support the discovered client."""


class InstallRefusedError(AgentIntegrationError):
    """Raised when the operator / installer policy refuses the install."""


class CapabilityMismatchError(AgentIntegrationError):
    """Raised when the installed client fails the version handshake."""


class AdapterError(AgentIntegrationError):
    """Generic adapter-level error (filesystem, parse, etc.)."""


@dataclass(frozen=True)
class VendorProfile:
    """The vendor profile the adapter is configured for.

    ``client_version`` is the version pinned at integration time;
    the adapter MUST refuse unknown combinations via
    :class:`UnsupportedClientError`.
    """

    vendor: str
    client_version: str
    schema_url: str = ""  # official schema / manifest URL the adapter validates


@dataclass(frozen=True)
class AdapterInstallResult:
    """The result of a successful install / configure cycle."""

    vendor: str
    installed_path: str
    skill_version: str
    mcp_endpoint: str
    preserved_user_entries: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class AdapterHealthReport:
    """The result of a :meth:`AgentIntegrationAdapter.health_check`."""

    vendor: str
    healthy: bool
    reason: str = ""
    details: Mapping[str, object] = None


class AgentIntegrationAdapter(abc.ABC):
    """§46 agent-integration adapter contract.

    The contract supports one-click setup while keeping installers
    replaceable. Adapters MUST NOT own retrieval / business rules;
    the actual knowledge / retrieval logic remains in the Project
    Intelligence core.
    """

    vendor: str = ""

    @abc.abstractmethod
    def detect(self, target_root: str) -> VendorProfile:
        """Detect the supported version installed in the target project.

        Raise :class:`UnsupportedClientError` when the discovery
        result does not match the supported profile.
        """

    @abc.abstractmethod
    def install(self, target_root: str, *, skill_version: str,
                mcp_endpoint: str,
                client_version: Optional[str] = None
                ) -> AdapterInstallResult: ...

    @abc.abstractmethod
    def configure_mcp(self, target_root: str, *,
                      mcp_endpoint: str) -> Sequence[str]:
        """Configure the MCP server endpoint in the owned config files.

        Returns the list of configuration paths that were
        created or modified.
        """

    @abc.abstractmethod
    def install_skill(self, target_root: str, *,
                      skill_version: str) -> Sequence[str]:
        """Install the canonical Agent Skill at the owned location."""

    @abc.abstractmethod
    def verify_compatibility(self, target_root: str) -> Mapping[str, str]:
        """Run the §39 compatibility handshake against the installed client.

        Empty mapping means OK; otherwise the mapping is
        ``{dimension: reason}``.
        """

    @abc.abstractmethod
    def health_check(self, target_root: str) -> AdapterHealthReport: ...

    @abc.abstractmethod
    def uninstall(self, target_root: str) -> Sequence[str]:
        """Remove the adapter-managed configuration; preserve user entries."""

    @abc.abstractmethod
    def describe(self) -> Mapping[str, str]:
        """Return a stable description of the adapter and supported profile."""
"""Phase 6 §46 default agent-integration adapter base class.

A thin convenience base providing vendor profile storage and
typed-error helpers. Concrete vendor adapters (Codex, Claude
Code, OpenCode, generic agent) inherit from this class and
override the eight operations of the documented contract.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from ...ports.agent_integration.adapter import (
    AdapterHealthReport,
    AdapterInstallResult,
    AgentIntegrationAdapter,
    InstallRefusedError,
    UnsupportedClientError,
    VendorProfile,
)


__all__ = ["DefaultAgentIntegrationAdapter", "ADAPTER_NAME_BASE"]


ADAPTER_NAME_BASE = "agent-integration-default-base"


class DefaultAgentIntegrationAdapter(AgentIntegrationAdapter):
    """§46 default adapter base.

    Subclasses set :attr:`vendor` and override the eight
    operations. The base records the supported vendor profile
    and refuses installation against unsupported clients.
    """

    vendor: str = "unknown"

    def __init__(self, *, vendor: str, client_version: str,
                 schema_url: str = ""):
        self.vendor = vendor
        self._profile = VendorProfile(
            vendor=vendor, client_version=client_version,
            schema_url=schema_url,
        )

    @property
    def profile(self) -> VendorProfile:
        return self._profile

    def detect(self, target_root: str) -> VendorProfile:
        """Default ``detect`` returns the pinned profile.

        Subclasses override to inspect the target project's
        installed vendor binaries and raise
        :class:`UnsupportedClientError` on mismatch.
        """
        return self._profile

    def install(self, target_root: str, *, skill_version: str,
                mcp_endpoint: str,
                client_version: Optional[str] = None
                ) -> AdapterInstallResult:
        # Subclasses MUST call configure_mcp + install_skill and
        # combine their outputs into the install result. The
        # default refuses installation against an unsupported
        # client version.
        if (client_version is not None
                and client_version != self._profile.client_version):
            raise UnsupportedClientError(
                f"adapter {self.vendor!r} supports client_version "
                f"{self._profile.client_version!r}, got "
                f"{client_version!r}"
            )
        if not mcp_endpoint:
            raise InstallRefusedError(
                "mcp_endpoint is required"
            )
        if not skill_version:
            raise InstallRefusedError(
                "skill_version is required"
            )
        configured = self.configure_mcp(
            target_root, mcp_endpoint=mcp_endpoint,
        )
        installed = self.install_skill(
            target_root, skill_version=skill_version,
        )
        return AdapterInstallResult(
            vendor=self.vendor,
            installed_path=target_root,
            skill_version=skill_version,
            mcp_endpoint=mcp_endpoint,
            preserved_user_entries=(),
            notes=f"installed: {', '.join(sorted(set(configured) | set(installed)))}",
        )

    def configure_mcp(self, target_root: str, *,
                      mcp_endpoint: str) -> Sequence[str]:
        # Subclasses override to write their MCP configuration.
        raise NotImplementedError(
            f"configure_mcp must be implemented by {self.__class__.__name__}"
        )

    def install_skill(self, target_root: str, *,
                      skill_version: str) -> Sequence[str]:
        # Subclasses override to install the canonical skill.
        raise NotImplementedError(
            f"install_skill must be implemented by {self.__class__.__name__}"
        )

    def verify_compatibility(self, target_root: str) -> Mapping[str, str]:
        return {}

    def health_check(self, target_root: str) -> AdapterHealthReport:
        return AdapterHealthReport(
            vendor=self.vendor, healthy=True,
            reason="default health check (no plugin configured)",
        )

    def uninstall(self, target_root: str) -> Sequence[str]:
        return ()

    def describe(self) -> Mapping[str, str]:
        return {
            "vendor": self.vendor,
            "client_version": self._profile.client_version,
            "schema_url": self._profile.schema_url,
        }
"""Phase 6 task 93 — agent integration adapter contract tests."""

from __future__ import annotations

import unittest

from pi_platform.core.agent_integration.adapter import (
    DefaultAgentIntegrationAdapter,
)
from pi_platform.ports.agent_integration.adapter import (
    AdapterHealthReport,
    AdapterInstallResult,
    AgentIntegrationAdapter,
    InstallRefusedError,
    UnsupportedClientError,
)


__all__ = ["AgentAdapterContractTests"]


class _StubAdapter(DefaultAgentIntegrationAdapter):
    """A minimal concrete adapter that records each operation."""

    def __init__(self):
        super().__init__(vendor="stub", client_version="1.0.0",
                         schema_url="https://example.com/schema.json")
        self.calls: list[str] = []

    def detect(self, target_root):
        self.calls.append("detect")
        return self.profile

    def install(self, target_root, *, skill_version, mcp_endpoint,
                client_version=None):
        self.calls.append("install")
        return super().install(target_root, skill_version=skill_version,
                               mcp_endpoint=mcp_endpoint,
                               client_version=client_version)

    def configure_mcp(self, target_root, *, mcp_endpoint):
        self.calls.append("configure_mcp")
        return [f"{target_root}/mcp.json"]

    def install_skill(self, target_root, *, skill_version):
        self.calls.append("install_skill")
        return [f"{target_root}/SKILL.md"]

    def verify_compatibility(self, target_root):
        self.calls.append("verify_compatibility")
        return {}

    def health_check(self, target_root):
        self.calls.append("health_check")
        return AdapterHealthReport(vendor=self.vendor, healthy=True,
                                   reason="healthy")

    def uninstall(self, target_root):
        self.calls.append("uninstall")
        return ()


class AgentAdapterContractTests(unittest.TestCase):

    def test_adapter_is_subclass_of_port(self):
        adapter = _StubAdapter()
        self.assertIsInstance(adapter, AgentIntegrationAdapter)

    def test_describe_reports_vendor_and_client_version(self):
        adapter = _StubAdapter()
        desc = adapter.describe()
        self.assertEqual(desc["vendor"], "stub")
        self.assertEqual(desc["client_version"], "1.0.0")

    def test_install_runs_all_eight_operations(self):
        adapter = _StubAdapter()
        result = adapter.install(
            "/tmp/proj", skill_version="1.4.0",
            mcp_endpoint="stdio://pi-mcp",
        )
        # detect is not invoked by install (caller responsibility),
        # but configure_mcp, install_skill, and the install wrapper
        # ARE invoked.
        self.assertIn("install", adapter.calls)
        self.assertIn("configure_mcp", adapter.calls)
        self.assertIn("install_skill", adapter.calls)
        self.assertIsInstance(result, AdapterInstallResult)
        self.assertEqual(result.vendor, "stub")
        self.assertEqual(result.skill_version, "1.4.0")
        self.assertEqual(result.mcp_endpoint, "stdio://pi-mcp")

    def test_install_refuses_unsupported_client_version(self):
        adapter = _StubAdapter()
        with self.assertRaises(UnsupportedClientError):
            adapter.install("/tmp/proj", skill_version="1.4.0",
                            mcp_endpoint="stdio://pi-mcp",
                            client_version="99.0.0")

    def test_install_refuses_missing_mcp_endpoint(self):
        adapter = _StubAdapter()
        with self.assertRaises(InstallRefusedError):
            adapter.install("/tmp/proj", skill_version="1.4.0",
                            mcp_endpoint="")

    def test_install_refuses_missing_skill_version(self):
        adapter = _StubAdapter()
        with self.assertRaises(InstallRefusedError):
            adapter.install("/tmp/proj", skill_version="",
                            mcp_endpoint="stdio://pi-mcp")

    def test_uninstall_does_not_raise(self):
        adapter = _StubAdapter()
        paths = adapter.uninstall("/tmp/proj")
        self.assertEqual(paths, ())

    def test_health_check_reports_healthy(self):
        adapter = _StubAdapter()
        report = adapter.health_check("/tmp/proj")
        self.assertTrue(report.healthy)
        self.assertEqual(report.vendor, "stub")

    def test_adapters_must_not_own_retrieval_logic(self):
        # The adapter contract does NOT expose retrieval,
        # LLM, or materialise methods. Adapters that try to
        # override such operations would break the contract.
        adapter = _StubAdapter()
        self.assertFalse(hasattr(adapter, "retrieve"))
        self.assertFalse(hasattr(adapter, "materialise"))
        self.assertFalse(hasattr(adapter, "build_task_context"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
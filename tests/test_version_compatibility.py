"""Phase 6 task 88 — version compatibility handshake tests."""

from __future__ import annotations

import unittest

from pi_platform.core.agent_integration.version_compatibility import (
    DefaultVersionCompatibilityPolicy,
)
from pi_platform.ports.agent_integration import (
    ClientCapabilityReport,
    CompatibilityRange,
    VersionCompatibilityError,
    VersionIncompatibleError,
    VersionRange,
)


__all__ = ["VersionCompatibilityTests"]


def _range(min_: str, max_: str) -> VersionRange:
    return VersionRange(minimum=min_, maximum_exclusive=max_)


def _client(**overrides) -> ClientCapabilityReport:
    base = dict(
        platform_version="0.8.0",
        mcp_api_version="1.3.0",
        knowledge_schema_version="0.7.0",
        skill_version="1.4.0",
        okf_profile_version="0.2",
        plugin_distribution_schema_version="1",
        a2a_adapter_version=None,
        agent_adapter_version=None,
        runtime_index_schema_version=None,
    )
    base.update(overrides)
    return ClientCapabilityReport(**base)


def _policy() -> DefaultVersionCompatibilityPolicy:
    return DefaultVersionCompatibilityPolicy(
        range_=CompatibilityRange(
            platform_version=_range("0.8.0", "1.0.0"),
            mcp_api_version=_range("1.3.0", "2.0.0"),
            knowledge_schema_version=_range("0.7.0", "1.0.0"),
            skill_version=_range("1.4.0", "2.0.0"),
            okf_profile_set=("0.2",),
            plugin_distribution_schema=("1",),
        ),
        adapter_name=None,
    )


class VersionCompatibilityTests(unittest.TestCase):

    def test_compatible_client_verifies(self):
        policy = _policy()
        policy.verify(_client())  # no exception

    def test_disjoint_mcp_api_raises_typed_error(self):
        policy = _policy()
        with self.assertRaises(VersionIncompatibleError) as cm:
            policy.verify(_client(mcp_api_version="2.0.0"))
        self.assertEqual(cm.exception.dimension, "mcpApiVersion")
        self.assertEqual(cm.exception.client_offered_value, "2.0.0")
        self.assertIn("1.3.0", cm.exception.server_offered_range)
        self.assertIn("upgrade", cm.exception.upgrade_instructions.lower())

    def test_disjoint_platform_version_raises_typed_error(self):
        policy = _policy()
        with self.assertRaises(VersionIncompatibleError) as cm:
            policy.verify(_client(platform_version="2.5.0"))
        self.assertEqual(cm.exception.dimension, "platformVersion")
        self.assertEqual(cm.exception.client_offered_value, "2.5.0")

    def test_missing_required_mcp_api_raises(self):
        policy = _policy()
        with self.assertRaises(VersionIncompatibleError) as cm:
            policy.verify(_client(mcp_api_version=None))
        self.assertEqual(cm.exception.dimension, "mcpApiVersion")
        self.assertEqual(cm.exception.client_offered_value, "")

    def test_missing_required_okf_raises(self):
        policy = _policy()
        with self.assertRaises(VersionIncompatibleError) as cm:
            policy.verify(_client(okf_profile_version=None))
        self.assertEqual(cm.exception.dimension, "okfProfileVersion")

    def test_missing_required_plugin_distribution_schema_raises(self):
        policy = _policy()
        with self.assertRaises(VersionIncompatibleError) as cm:
            policy.verify(_client(plugin_distribution_schema_version=None))
        self.assertEqual(cm.exception.dimension,
                         "pluginDistributionSchemaVersion")

    def test_unknown_okf_version_raises(self):
        policy = _policy()
        with self.assertRaises(VersionIncompatibleError) as cm:
            policy.verify(_client(okf_profile_version="0.3"))
        self.assertEqual(cm.exception.dimension, "okfProfileVersion")
        self.assertEqual(cm.exception.client_offered_value, "0.3")

    def test_optional_knowledge_schema_skipped_when_absent(self):
        policy = _policy()
        policy.verify(_client(knowledge_schema_version=None))

    def test_optional_knowledge_schema_out_of_range_raises(self):
        policy = _policy()
        with self.assertRaises(VersionIncompatibleError) as cm:
            policy.verify(_client(knowledge_schema_version="2.5.0"))
        self.assertEqual(cm.exception.dimension, "knowledgeSchemaVersion")

    def test_optional_skill_version_skipped_when_absent(self):
        policy = _policy()
        policy.verify(_client(skill_version=None))

    def test_optional_skill_version_out_of_range_raises(self):
        policy = _policy()
        with self.assertRaises(VersionIncompatibleError) as cm:
            policy.verify(_client(skill_version="2.5.0"))
        self.assertEqual(cm.exception.dimension, "skillVersion")

    def test_a2a_adapter_unavailable_skipped(self):
        policy = _policy()
        policy.verify(_client(a2a_adapter_version=None))

    def test_runtime_index_schema_unavailable_skipped(self):
        policy = _policy()
        policy.verify(_client(runtime_index_schema_version=None))

    def test_client_runtime_index_schema_unavailable_rejected(self):
        policy = _policy()
        with self.assertRaises(VersionIncompatibleError) as cm:
            policy.verify(_client(runtime_index_schema_version="0.1.0"))
        self.assertEqual(cm.exception.dimension,
                         "runtimeIndexSchemaVersion")
        self.assertEqual(cm.exception.server_offered_range, "(unavailable)")

    def test_serialise_is_byte_stable(self):
        policy = _policy()
        first = policy.serialise()
        second = policy.serialise()
        self.assertEqual(first, second)

    def test_serialise_includes_all_9_dimensions(self):
        policy = _policy()
        import json
        payload = json.loads(policy.serialise())
        for dim in ("platformVersion", "mcpApiVersion",
                     "a2aAdapterVersion", "knowledgeSchemaVersion",
                     "okfProfileVersion", "skillVersion",
                     "pluginDistributionSchemaVersion",
                     "agentAdapterVersion", "runtimeIndexSchemaVersion"):
            self.assertIn(dim, payload, msg=f"missing {dim}")

    def test_version_range_parsing_rejects_malformed(self):
        with self.assertRaises(VersionCompatibilityError):
            from pi_platform.ports.agent_integration import _semver_range
            _semver_range("not-a-range")

    def test_version_range_constructor_rejects_equal_endpoints(self):
        with self.assertRaises(ValueError):
            VersionRange(minimum="1.0.0", maximum_exclusive="1.0.0")

    def test_version_range_constructor_rejects_non_semver(self):
        with self.assertRaises(ValueError):
            VersionRange(minimum="abc", maximum_exclusive="2.0.0")

    def test_upgrade_hint_mentions_adapter_when_named(self):
        policy = DefaultVersionCompatibilityPolicy(
            range_=CompatibilityRange(
                platform_version=_range("0.8.0", "1.0.0"),
                mcp_api_version=_range("1.3.0", "2.0.0"),
                knowledge_schema_version=_range("0.7.0", "1.0.0"),
                skill_version=_range("1.4.0", "2.0.0"),
                okf_profile_set=("0.2",),
                plugin_distribution_schema=("1",),
            ),
            adapter_name="codex",
        )
        try:
            policy.verify(_client(platform_version="2.5.0"))
        except VersionIncompatibleError as exc:
            self.assertEqual(exc.applicable_adapter, "codex")
            self.assertIn("codex", exc.upgrade_instructions)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
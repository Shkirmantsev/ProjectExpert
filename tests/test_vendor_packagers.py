"""Phase 6 task 89-92 — per-vendor packager tests + shared build runner."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pi_platform.adapters.agent_integration.packagers.claude_code import (
    ClaudeCodePluginPackager,
)
from pi_platform.adapters.agent_integration.packagers.codex import (
    CodexPluginPackager, ReleaseInputSet,
)
from pi_platform.adapters.agent_integration.packagers.generic_agent import (
    GenericAgentBundlePackager,
)
from pi_platform.adapters.agent_integration.packagers.opencode import (
    OpenCodePluginPackager,
)
from pi_platform.adapters.agent_integration.packagers.runner import (
    DeterministicBuildError,
    DeterministicBuildRunner,
)
from pi_platform.core.agent_integration.supply_chain_gate import (
    PluginSupplyChainSecurityGate,
)


__all__ = [
    "CodexPluginTests",
    "ClaudeCodePluginTests",
    "OpenCodePluginTests",
    "GenericAgentBundleTests",
    "DeterministicBuildRunnerTests",
]


def _skill_root(tmp: Path) -> Path:
    skill_dir = tmp / "skills" / "project-intelligence"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_bytes(
        b"---\nname: project-intelligence\nversion: 1.4.0\n"
        b"description: Test\nlicense: Apache-2.0\n---\n\n"
        b"# Test Skill\n",
    )
    refs = skill_dir / "references"
    refs.mkdir()
    (refs / "MCP-TOOLS.md").write_bytes(b"# tools\n")
    return tmp / "skills"


def _release() -> ReleaseInputSet:
    return ReleaseInputSet(
        skill_version="1.4.0",
        skill_sha256="abc123",
        mcp_api_range=">=1.3.0 <2.0.0",
        license="Apache-2.0",
        server_version="0.8.0",
        mcp_endpoint="stdio://pi-mcp",
        okf_profile_versions=("0.2",),
        source_repository="https://example.com/repo",
        permissions={"network": "outbound-only"},
        network_requirements={"outbound": ["localhost:stdio"]},
        agent_adapters={"codex": "1.0.0", "claude-code": "1.0.0",
                        "opencode": "1.0.0"},
    )


def _gate() -> PluginSupplyChainSecurityGate:
    return PluginSupplyChainSecurityGate(
        shared_release_identity={
            "skillSha256": "abc123",
            "serverVersion": "0.8.0",
            "mcpApiRange": ">=1.3.0 <2.0.0",
            "license": "Apache-2.0",
        },
    )


class _BundleTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.skills_root = _skill_root(self.tmp)
        self.release = _release()
        self.gate = _gate()


class CodexPluginTests(_BundleTestCase):

    def test_packager_generates_plugin_manifest(self):
        packager = CodexPluginPackager(
            skills_root=self.skills_root, gate=self.gate,
        )
        out = self.tmp / "dist"
        verdict = packager.package(self.release, output_root=out)
        self.assertTrue(verdict.passed, verdict.failing())
        bundle = out / "codex"
        manifest = json.loads(
            (bundle / "plugin.json").read_text())
        self.assertEqual(manifest["version"], "1.4.0")
        self.assertEqual(manifest["skills"][0]["sha256"], "abc123")
        self.assertEqual(manifest["mcp"]["endpoint"], "stdio://pi-mcp")
        # SKILL.md byte-equal to canonical
        bundled_skill = (bundle / "skills" / "project-intelligence"
                          / "SKILL.md").read_bytes()
        self.assertEqual(
            bundled_skill,
            (self.skills_root / "project-intelligence" / "SKILL.md"
             ).read_bytes())

    def test_legacy_fallback_emitted_when_configured(self):
        packager = CodexPluginPackager(
            skills_root=self.skills_root, gate=self.gate,
            legacy_support=True,
        )
        out = self.tmp / "dist"
        packager.package(self.release, output_root=out)
        self.assertTrue((out / "codex" / ".codex-plugin"
                         / "plugin.json").is_file())

    def test_legacy_fallback_absent_by_default(self):
        packager = CodexPluginPackager(
            skills_root=self.skills_root, gate=self.gate,
        )
        out = self.tmp / "dist"
        packager.package(self.release, output_root=out)
        self.assertFalse((out / "codex" / ".codex-plugin").exists())

    def test_two_runs_are_byte_identical(self):
        packager = CodexPluginPackager(
            skills_root=self.skills_root, gate=self.gate,
        )
        out1 = self.tmp / "dist1"
        out2 = self.tmp / "dist2"
        packager.package(self.release, output_root=out1)
        packager.package(self.release, output_root=out2)
        first = CodexPluginPackager.bundle_inventory(out1 / "codex")
        second = CodexPluginPackager.bundle_inventory(out2 / "codex")
        self.assertEqual(first, second)


class ClaudeCodePluginTests(_BundleTestCase):

    def test_packager_emits_claude_layout(self):
        packager = ClaudeCodePluginPackager(
            skills_root=self.skills_root, gate=self.gate,
        )
        out = self.tmp / "dist"
        verdict = packager.package(self.release, output_root=out)
        self.assertTrue(verdict.passed, verdict.failing())
        bundle = out / "claude-code"
        self.assertTrue((bundle / ".claude-plugin"
                         / "plugin.json").is_file())
        self.assertTrue((bundle / ".mcp.json").is_file())
        self.assertTrue((bundle / "README.md").is_file())
        manifest = json.loads(
            (bundle / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["slug"], "project-intelligence")
        self.assertEqual(manifest["version"], "1.4.0")

    def test_two_runs_are_byte_identical(self):
        packager = ClaudeCodePluginPackager(
            skills_root=self.skills_root, gate=self.gate,
        )
        out1 = self.tmp / "dist1"
        out2 = self.tmp / "dist2"
        packager.package(self.release, output_root=out1)
        packager.package(self.release, output_root=out2)
        first = ClaudeCodePluginPackager.bundle_inventory(
            out1 / "claude-code")
        second = ClaudeCodePluginPackager.bundle_inventory(
            out2 / "claude-code")
        self.assertEqual(first, second)


class OpenCodePluginTests(_BundleTestCase):

    def test_packager_emits_opencode_layout(self):
        packager = OpenCodePluginPackager(
            skills_root=self.skills_root, gate=self.gate,
        )
        out = self.tmp / "dist"
        verdict = packager.package(self.release, output_root=out)
        self.assertTrue(verdict.passed, verdict.failing())
        bundle = out / "opencode"
        self.assertTrue((bundle / "package.json").is_file())
        self.assertTrue((bundle / "plugin"
                         / "project-intelligence.ts").is_file())
        self.assertTrue((bundle / "config"
                         / "opencode.example.jsonc").is_file())
        # Skill embedded
        self.assertTrue((bundle / "skill" / "project-intelligence"
                         / "SKILL.md").is_file())

    def test_bootstrap_fallback_replaces_skill_with_instructions(self):
        packager = OpenCodePluginPackager(
            skills_root=self.skills_root, gate=self.gate,
            bootstrap_fallback=True,
        )
        out = self.tmp / "dist"
        packager.package(self.release, output_root=out)
        bundle = out / "opencode"
        # SKILL.md is NOT present (no Agent Skills support).
        self.assertFalse((bundle / "skill" / "project-intelligence"
                          / "SKILL.md").exists())
        self.assertTrue((bundle / "skill" / "project-intelligence"
                         / "README.md").is_file())

    def test_two_runs_are_byte_identical(self):
        packager = OpenCodePluginPackager(
            skills_root=self.skills_root, gate=self.gate,
        )
        out1 = self.tmp / "dist1"
        out2 = self.tmp / "dist2"
        packager.package(self.release, output_root=out1)
        packager.package(self.release, output_root=out2)
        first = OpenCodePluginPackager.bundle_inventory(
            out1 / "opencode")
        second = OpenCodePluginPackager.bundle_inventory(
            out2 / "opencode")
        self.assertEqual(first, second)


class GenericAgentBundleTests(_BundleTestCase):

    def test_bundle_emits_required_files(self):
        packager = GenericAgentBundlePackager(
            skills_root=self.skills_root, gate=self.gate,
        )
        out = self.tmp / "dist"
        verdict = packager.package(self.release, output_root=out)
        self.assertTrue(verdict.passed, verdict.failing())
        bundle = out / "generic-agent"
        self.assertTrue((bundle / "mcp" / "stdio-example.json").is_file())
        self.assertTrue((bundle / "mcp" / "http-example.json").is_file())
        self.assertTrue((bundle / "AGENTS.example.md").is_file())
        self.assertTrue((bundle / "README.md").is_file())
        self.assertTrue((bundle / "skills" / "project-intelligence"
                         / "SKILL.md").is_file())

    def test_skill_byte_equal_to_canonical(self):
        packager = GenericAgentBundlePackager(
            skills_root=self.skills_root, gate=self.gate,
        )
        out = self.tmp / "dist"
        packager.package(self.release, output_root=out)
        bundled = (out / "generic-agent" / "skills"
                   / "project-intelligence" / "SKILL.md").read_bytes()
        canonical = (self.skills_root / "project-intelligence"
                     / "SKILL.md").read_bytes()
        self.assertEqual(bundled, canonical)

    def test_two_runs_are_byte_identical(self):
        packager = GenericAgentBundlePackager(
            skills_root=self.skills_root, gate=self.gate,
        )
        out1 = self.tmp / "dist1"
        out2 = self.tmp / "dist2"
        packager.package(self.release, output_root=out1)
        packager.package(self.release, output_root=out2)
        first = GenericAgentBundlePackager.bundle_inventory(
            out1 / "generic-agent")
        second = GenericAgentBundlePackager.bundle_inventory(
            out2 / "generic-agent")
        self.assertEqual(first, second)


class DeterministicBuildRunnerTests(_BundleTestCase):

    def test_runner_emits_four_bundles(self):
        runner = DeterministicBuildRunner(
            skills_root=self.skills_root, gate=self.gate,
        )
        out = self.tmp / "dist"
        result = runner.build(self.release, output_root=out)
        self.assertEqual(set(result.verdicts.keys()),
                         {"codex", "claude-code", "opencode",
                          "generic-agent"})

    def test_runner_inventory_is_byte_identical_across_runs(self):
        runner = DeterministicBuildRunner(
            skills_root=self.skills_root, gate=self.gate,
        )
        out1 = self.tmp / "dist1"
        out2 = self.tmp / "dist2"
        runner.build(self.release, output_root=out1)
        runner.build(self.release, output_root=out2)
        inv1 = DeterministicBuildRunner.combined_inventory(
            runner.build(self.release, output_root=out1))
        inv2 = DeterministicBuildRunner.combined_inventory(
            runner.build(self.release, output_root=out2))
        self.assertEqual(inv1, inv2)

    def test_runner_provenance_carries_supply_chain_verdict(self):
        runner = DeterministicBuildRunner(
            skills_root=self.skills_root, gate=self.gate,
        )
        out = self.tmp / "dist"
        runner.build(self.release, output_root=out)
        for vendor_dir in sorted(p for p in out.iterdir() if p.is_dir()):
            provenance = json.loads(
                (vendor_dir / "PROVENANCE.json").read_text())
            self.assertIn("supplyChainGate", provenance)
            self.assertTrue(provenance["supplyChainGate"]["passed"])

    def test_runner_rejects_supply_chain_failures(self):
        bad_release = ReleaseInputSet(
            skill_version="1.4.0",
            skill_sha256="abc123",
            mcp_api_range=">=1.3.0 <2.0.0",
            license="Proprietary-1.0",  # not on the allow-list
            server_version="0.8.0",
            mcp_endpoint="stdio://pi-mcp",
            okf_profile_versions=("0.2",),
            source_repository="https://example.com/repo",
            permissions={},
            network_requirements={},
        )
        runner = DeterministicBuildRunner(
            skills_root=self.skills_root, gate=_gate(),
        )
        with self.assertRaises(DeterministicBuildError):
            runner.build(bad_release, output_root=self.tmp / "dist")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
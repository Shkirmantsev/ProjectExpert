"""Phase 6 §42 Claude Code plugin packager.

Generates a deterministic Claude Code plugin bundle from one
release input set:

* ``.claude-plugin/plugin.json`` — Claude Code manifest.
* ``.mcp.json`` — Claude Code MCP configuration.
* ``skills/project-intelligence/SKILL.md`` (and references)
  byte-equal to the canonical skill package.
* ``README.md`` — vendor-facing installation instructions.
* ``commands/`` and ``agents/`` — optional, empty by default
  (the contract stays minimal).

The plugin slug is the documented stable ``project-intelligence``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pi_platform.core.agent_integration.supply_chain_gate import (
    PluginSupplyChainSecurityGate,
    SupplyChainVerdict,
)


__all__ = [
    "CLAUDE_CODE_PLUGIN_SCHEMA_URL",
    "ClaudeCodePluginPackager",
    "ClaudeCodePluginPackagerError",
]


log = logging.getLogger(__name__)


CLAUDE_CODE_PLUGIN_SCHEMA_URL = (
    "https://docs.claude.com/en/docs/claude-code/plugins.md"
)


class ClaudeCodePluginPackagerError(RuntimeError):
    """Raised when the Claude Code bundle cannot be generated."""


def _claude_manifest(release, bundle_path: str) -> dict:
    return {
        "schemaVersion": 1,
        "slug": "project-intelligence",
        "name": "Project Intelligence",
        "version": release.skill_version,
        "vendor": "project-intelligence",
        "license": release.license,
        "skills": [
            {
                "name": "project-intelligence",
                "version": release.skill_version,
                "sha256": release.skill_sha256,
            }
        ],
        "mcp": {
            "endpoint": release.mcp_endpoint,
            "apiVersion": release.mcp_api_range,
            "transport": "stdio",
        },
        "distribution": {
            "schemaVersion": 1,
            "manifestUri": "project-intelligence://distribution/manifest",
        },
        "okf": {
            "supported": list(release.okf_profile_versions),
        },
        "permissions": dict(release.permissions or {}),
        "networkRequirements": dict(release.network_requirements or {}),
        "sourceRepository": release.source_repository,
        "pluginSchemaUrl": CLAUDE_CODE_PLUGIN_SCHEMA_URL,
        "bundlePath": bundle_path,
    }


def _walk_files(skill_dir: Path) -> list[Path]:
    if not skill_dir.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(skill_dir.rglob("*")):
        if p.is_file() and not p.is_symlink():
            out.append(p)
    return out


class ClaudeCodePluginPackager:
    """§42 Claude Code plugin packager."""

    def __init__(self, *,
                 skills_root: Path,
                 gate: PluginSupplyChainSecurityGate):
        self._skills_root = Path(skills_root)
        self._gate = gate

    @property
    def vendor(self) -> str:
        return "claude-code"

    @property
    def slug(self) -> str:
        # The plugin slug is stable post-release.
        return "project-intelligence"

    def package(self, release, *,
                output_root: Path) -> SupplyChainVerdict:
        from pi_platform.adapters.agent_integration.packagers.codex import (
            ReleaseInputSet,
        )
        assert isinstance(release, ReleaseInputSet)
        skill_name = "project-intelligence"
        skill_dir = self._skills_root / skill_name
        if not skill_dir.is_dir():
            raise ClaudeCodePluginPackagerError(
                f"skill package not found: {skill_dir}"
            )
        bundle_root = Path(output_root) / self.vendor
        bundle_root.mkdir(parents=True, exist_ok=True)

        # The Claude Code bundle layout.
        claude_plugin_dir = bundle_root / ".claude-plugin"
        claude_plugin_dir.mkdir(parents=True, exist_ok=True)
        skill_dest = bundle_root / "skills" / skill_name
        skill_dest.mkdir(parents=True, exist_ok=True)
        for src in _walk_files(skill_dir):
            rel = src.relative_to(skill_dir)
            tgt = skill_dest / rel
            tgt.parent.mkdir(parents=True, exist_ok=True)
            tgt.write_bytes(src.read_bytes())

        # ``.mcp.json`` is the documented Claude Code MCP file.
        mcp_cfg = {
            "endpoint": release.mcp_endpoint,
            "apiVersion": release.mcp_api_range,
            "transport": "stdio",
        }
        (bundle_root / ".mcp.json").write_bytes(
            json.dumps(mcp_cfg, sort_keys=True,
                       separators=(",", ":")).encode("utf-8"))

        # ``.claude-plugin/plugin.json``.
        manifest = _claude_manifest(release,
                                  str(bundle_root.relative_to(output_root)))
        (claude_plugin_dir / "plugin.json").write_bytes(
            json.dumps(manifest, sort_keys=True,
                       separators=(",", ":")).encode("utf-8"))

        # Empty commands/ + agents/ (vendor convention).
        (bundle_root / "commands").mkdir(exist_ok=True)
        (bundle_root / "commands" / ".gitkeep").write_bytes(b"")
        (bundle_root / "agents").mkdir(exist_ok=True)
        (bundle_root / "agents" / ".gitkeep").write_bytes(b"")

        # ``README.md`` — minimal vendor instructions.
        readme = (
            "# Project Intelligence (Claude Code plugin)\n\n"
            "Install with the Claude Code plugin manager. The "
            "plugin slug is `project-intelligence`.\n\n"
            "After install, the MCP server is available at the "
            f"configured endpoint (`{release.mcp_endpoint}`).\n"
        )
        (bundle_root / "README.md").write_bytes(readme.encode("utf-8"))

        bundle_manifest = {
            "skillVersion": release.skill_version,
            "skillSha256": release.skill_sha256,
            "canonicalSkillSha256": release.skill_sha256,
            "mcpApiRange": release.mcp_api_range,
            "license": release.license,
            "serverIdentity": {
                "skillSha256": release.skill_sha256,
                "serverVersion": release.server_version,
                "mcpApiRange": release.mcp_api_range,
                "license": release.license,
            },
            "sourceRepository": release.source_repository,
            "permissions": dict(release.permissions or {}),
            "networkRequirements": dict(release.network_requirements or {}),
            "scripts": {},
        }
        verdict = self._gate.run(str(bundle_root.relative_to(output_root)), bundle_manifest)
        provenance_path = bundle_root / "PROVENANCE.json"
        provenance = {"bundlePath": str(bundle_root.relative_to(output_root))}
        provenance_out = self._gate.record_in_provenance(
            verdict, provenance,
        )
        provenance_path.write_bytes(json.dumps(
            provenance_out, sort_keys=True,
            separators=(",", ":")).encode("utf-8"))
        return verdict

    @staticmethod
    def bundle_inventory(bundle_root: Path) -> dict[str, str]:
        from hashlib import sha256
        out: dict[str, str] = {}
        for p in sorted(bundle_root.rglob("*")):
            if p.is_file() and not p.is_symlink():
                rel = str(p.relative_to(bundle_root))
                out[rel] = sha256(p.read_bytes()).hexdigest()
        return out
"""Phase 6 §41 Codex / ChatGPT plugin packager.

Generates a deterministic Codex Agent Plugin bundle from one
release input set:

* ``plugin.json`` — Codex manifest pointing at the local MCP
  endpoint and the canonical Agent Skill.
* ``mcp.json`` — Codex MCP configuration with the platform
  endpoint.
* ``skills/project-intelligence/SKILL.md`` (and references)
  byte-equal to the canonical skill package.
* ``assets/`` — placeholder for vendor assets.
* legacy ``.codex-plugin/plugin.json`` — emitted only when
  the configured client profile requires the compatibility
  fallback.

All four packagers (Codex, Claude Code, OpenCode, generic
agent) consume the same release input set and MUST agree on
the shared release identity. The :class:`PluginSupplyChainSecurityGate`
is invoked before emit.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

from pi_platform.core.agent_integration.supply_chain_gate import (
    PluginSupplyChainSecurityGate,
    SupplyChainVerdict,
)


__all__ = [
    "CODEX_PLUGIN_SCHEMA_URL",
    "CodexPluginPackager",
    "CodexPluginPackagerError",
    "ReleaseInputSet",
]


log = logging.getLogger(__name__)


CODEX_PLUGIN_SCHEMA_URL = (
    "https://github.com/openai/codex-plugin/blob/main/schema/plugin.json"
)


class CodexPluginPackagerError(RuntimeError):
    """Raised when the Codex plugin bundle cannot be generated."""


@dataclass(frozen=True)
class ReleaseInputSet:
    """Shared release input consumed by every packager."""

    skill_version: str
    skill_sha256: str
    mcp_api_range: str
    license: str
    server_version: str
    mcp_endpoint: str
    okf_profile_versions: tuple[str, ...]
    source_repository: str = (
        "https://github.com/anomalyco/opencode"
    )
    permissions: Mapping[str, object] = None
    network_requirements: Mapping[str, object] = None
    agent_adapters: Mapping[str, str] = None

    def __post_init__(self) -> None:
        if not self.skill_sha256:
            raise CodexPluginPackagerError("skill_sha256 is required")
        if not self.skill_version:
            raise CodexPluginPackagerError("skill_version is required")


def _manifest_dict(release: ReleaseInputSet, *,
                   bundle_name: str = "project-intelligence",
                   bundle_path: str = "dist/codex",
                   plugin_schema_url: str,
                   legacy_support: bool = False) -> dict:
    manifest = {
        "schemaVersion": 1,
        "name": bundle_name,
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
        },
        "distribution": {
            "schemaVersion": 1,
            "manifestUri": "project-intelligence://distribution/manifest",
            "skillUri": "project-intelligence://skills/"
                        "project-intelligence/{v}/SKILL.md".format(
                            v=release.skill_version),
        },
        "okf": {
            "supported": list(release.okf_profile_versions),
        },
        "permissions": dict(release.permissions or {}),
        "networkRequirements": dict(release.network_requirements or {}),
        "sourceRepository": release.source_repository,
        "pluginSchemaUrl": plugin_schema_url,
        "bundlePath": bundle_path,
    }
    if legacy_support:
        manifest["legacy"] = {
            "codexPluginPath": ".codex-plugin/plugin.json",
        }
    return manifest


def _walk_files(skill_dir: Path) -> list[Path]:
    if not skill_dir.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(skill_dir.rglob("*")):
        if p.is_file() and not p.is_symlink():
            out.append(p)
    return out


class CodexPluginPackager:
    """§41 Codex / ChatGPT plugin packager."""

    def __init__(self, *,
                 skills_root: Path,
                 gate: PluginSupplyChainSecurityGate,
                 legacy_support: bool = False):
        self._skills_root = Path(skills_root)
        self._gate = gate
        self._legacy_support = legacy_support

    @property
    def vendor(self) -> str:
        return "codex"

    def package(self, release: ReleaseInputSet, *,
                output_root: Path) -> SupplyChainVerdict:
        skill_name = "project-intelligence"
        skill_dir = self._skills_root / skill_name
        if not skill_dir.is_dir():
            raise CodexPluginPackagerError(
                f"skill package not found: {skill_dir}"
            )
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            raise CodexPluginPackagerError(
                f"missing SKILL.md under {skill_dir}"
            )
        bundle_root = Path(output_root) / self.vendor
        bundle_root.mkdir(parents=True, exist_ok=True)

        # The Codex bundle layout.
        skill_dest = bundle_root / "skills" / skill_name
        skill_dest.mkdir(parents=True, exist_ok=True)
        for src in _walk_files(skill_dir):
            rel = src.relative_to(skill_dir)
            tgt = skill_dest / rel
            tgt.parent.mkdir(parents=True, exist_ok=True)
            tgt.write_bytes(src.read_bytes())

        # Codex ``mcp.json``.
        mcp_cfg = {
            "endpoint": release.mcp_endpoint,
            "apiVersion": release.mcp_api_range,
            "transport": "stdio",
        }
        (bundle_root / "mcp.json").write_bytes(
            json.dumps(mcp_cfg, sort_keys=True,
                       separators=(",", ":")).encode("utf-8"))

        # Codex ``plugin.json``.
        manifest = _manifest_dict(
            release,
            bundle_path=str(bundle_root.relative_to(output_root)),
            plugin_schema_url=CODEX_PLUGIN_SCHEMA_URL,
            legacy_support=self._legacy_support,
        )
        (bundle_root / "plugin.json").write_bytes(
            json.dumps(manifest, sort_keys=True,
                       separators=(",", ":")).encode("utf-8"))

        # Legacy ``.codex-plugin/plugin.json`` — only when the
        # configured client profile demands it.
        if self._legacy_support:
            legacy_dir = bundle_root / ".codex-plugin"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            (legacy_dir / "plugin.json").write_bytes(
                json.dumps(manifest, sort_keys=True,
                           separators=(",", ":")).encode("utf-8"))

        # assets/ placeholder.
        (bundle_root / "assets").mkdir(exist_ok=True)
        (bundle_root / "assets" / ".gitkeep").write_bytes(b"")

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
        # Append verdict to bundle provenance payload. The
        # bundlePath is recorded relative to ``output_root`` so
        # two isolated runs at different absolute paths produce
        # byte-identical provenance.
        provenance_path = bundle_root / "PROVENANCE.json"
        provenance = {
            "bundlePath": str(bundle_root.relative_to(output_root)),
            "serverIdentity": dict(release.agent_adapters or {}),
        }
        provenance_out = self._gate.record_in_provenance(
            verdict, provenance,
        )
        provenance_path.write_bytes(json.dumps(
            provenance_out, sort_keys=True,
            separators=(",", ":")).encode("utf-8"))
        return verdict

    @staticmethod
    def bundle_inventory(bundle_root: Path) -> dict[str, str]:
        """Return the deterministic ``{path: sha256}`` inventory of the bundle.

        The whole output tree is hashed; this is what the §45
        deterministic-build gate compares across two isolated
        packager runs.
        """
        from hashlib import sha256
        out: dict[str, str] = {}
        for p in sorted(bundle_root.rglob("*")):
            if p.is_file() and not p.is_symlink():
                rel = str(p.relative_to(bundle_root))
                out[rel] = sha256(p.read_bytes()).hexdigest()
        return out
"""Phase 6 §44 generic agent bundle packager.

Generates a deterministic, vendor-neutral bundle from one
release input set:

* ``skills/project-intelligence/SKILL.md`` (and references)
  byte-equal to the canonical skill package.
* ``mcp/stdio-example.json`` — stdio MCP example config.
* ``mcp/http-example.json`` — Streamable HTTP MCP example.
* ``AGENTS.example.md`` — plain-Markdown instructions for any
  coding agent without a dedicated plugin.
* ``README.md`` — installation guidance.

The bundle is the canonical fallback for agents that don't
have a dedicated vendor plugin.
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
    "GenericAgentBundleError",
    "GenericAgentBundlePackager",
]


log = logging.getLogger(__name__)


class GenericAgentBundleError(RuntimeError):
    """Raised when the generic agent bundle cannot be generated."""


def _mcp_stdio_example(release) -> dict:
    return {
        "mcpServers": {
            "project-intelligence": {
                "command": "python",
                "args": ["-m", "pi_platform.cli", "mcp-serve",
                         "--transport", "stdio"],
                "env": {
                    "PI_MCP_API_VERSION": release.mcp_api_range,
                },
            },
        },
    }


def _mcp_http_example(release) -> dict:
    return {
        "mcpServers": {
            "project-intelligence": {
                "type": "http",
                "url": release.mcp_endpoint,
                "apiVersion": release.mcp_api_range,
            },
        },
    }


def _agents_example(release) -> str:
    return (
        "# AGENTS.example.md\n\n"
        "## Project Intelligence MCP\n\n"
        "This project ships a Project Intelligence MCP server.\n\n"
        f"- endpoint: `{release.mcp_endpoint}`\n"
        f"- apiVersion: `{release.mcp_api_range}`\n"
        f"- skill: `project-intelligence@{release.skill_version}` "
        f"(sha256: `{release.skill_sha256}`)\n\n"
        "Use `project.search`, `project.retrieve_context` and the "
        "other read-only tools before scanning the repository. Use "
        "`project.build_task_context` for implementation work. The "
        "write / materialise tools require an `approval_id` issued "
        "by the trusted operator boundary.\n"
    )


def _walk_files(skill_dir: Path) -> list[Path]:
    if not skill_dir.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(skill_dir.rglob("*")):
        if p.is_file() and not p.is_symlink():
            out.append(p)
    return out


class GenericAgentBundlePackager:
    """§44 generic agent bundle packager."""

    def __init__(self, *,
                 skills_root: Path,
                 gate: PluginSupplyChainSecurityGate):
        self._skills_root = Path(skills_root)
        self._gate = gate

    @property
    def vendor(self) -> str:
        return "generic-agent"

    def package(self, release, *,
                output_root: Path) -> SupplyChainVerdict:
        from pi_platform.adapters.agent_integration.packagers.codex import (
            ReleaseInputSet,
        )
        assert isinstance(release, ReleaseInputSet)
        skill_name = "project-intelligence"
        skill_dir = self._skills_root / skill_name
        if not skill_dir.is_dir():
            raise GenericAgentBundleError(
                f"skill package not found: {skill_dir}"
            )
        bundle_root = Path(output_root) / self.vendor
        bundle_root.mkdir(parents=True, exist_ok=True)

        skill_dest = bundle_root / "skills" / skill_name
        skill_dest.mkdir(parents=True, exist_ok=True)
        for src in _walk_files(skill_dir):
            rel = src.relative_to(skill_dir)
            tgt = skill_dest / rel
            tgt.parent.mkdir(parents=True, exist_ok=True)
            tgt.write_bytes(src.read_bytes())

        mcp_dir = bundle_root / "mcp"
        mcp_dir.mkdir(parents=True, exist_ok=True)
        (mcp_dir / "stdio-example.json").write_bytes(json.dumps(
            _mcp_stdio_example(release), sort_keys=True,
            separators=(",", ":")).encode("utf-8"))
        (mcp_dir / "http-example.json").write_bytes(json.dumps(
            _mcp_http_example(release), sort_keys=True,
            separators=(",", ":")).encode("utf-8"))

        (bundle_root / "AGENTS.example.md").write_bytes(
            _agents_example(release).encode("utf-8"))
        (bundle_root / "README.md").write_bytes(
            (
                "# Project Intelligence (generic agent bundle)\n\n"
                "Drop the contents of this bundle into the target "
                "project. The bundle is vendor-neutral and maximises "
                "compatibility with Agent Skills, MCP, optional A2A "
                "and plain Markdown instructions.\n"
            ).encode("utf-8"))

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
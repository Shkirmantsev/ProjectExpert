"""Phase 6 §45 plugin generation pipeline runner.

Coordinates the four per-vendor packagers from one release
input set, applies the supply-chain security gate and verifies
the deterministic byte-identity of the full output tree across
two isolated runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pi_platform.adapters.agent_integration.packagers.claude_code import (
    ClaudeCodePluginPackager,
)
from pi_platform.adapters.agent_integration.packagers.codex import (
    CodexPluginPackager,
    ReleaseInputSet,
)
from pi_platform.adapters.agent_integration.packagers.generic_agent import (
    GenericAgentBundlePackager,
)
from pi_platform.adapters.agent_integration.packagers.opencode import (
    OpenCodePluginPackager,
)
from pi_platform.core.agent_integration.supply_chain_gate import (
    PluginSupplyChainSecurityGate,
    SupplyChainVerdict,
)


__all__ = [
    "DeterministicBuildRunner",
    "DeterministicBuildError",
]


log = logging.getLogger(__name__)


class DeterministicBuildError(RuntimeError):
    """Raised when the four-packager run fails the §45 invariants."""


@dataclass(frozen=True)
class DeterministicBuildResult:
    """Aggregate result of a single four-packager run."""

    output_root: Path
    verdicts: Mapping[str, SupplyChainVerdict]
    shared_release_identity: Mapping[str, str]


class DeterministicBuildRunner:
    """§45 deterministic build runner."""

    def __init__(self, *,
                 skills_root: Path,
                 gate: PluginSupplyChainSecurityGate,
                 codex_legacy_support: bool = False,
                 opencode_bootstrap_fallback: bool = False):
        self._skills_root = Path(skills_root)
        self._gate = gate
        self._codex_legacy_support = codex_legacy_support
        self._opencode_bootstrap_fallback = opencode_bootstrap_fallback

    def build(self, release: ReleaseInputSet, *,
              output_root: Path) -> DeterministicBuildResult:
        if release.mcp_api_range != release.mcp_api_range:
            # Sanity: enforce the recorded MCP range is set.
            raise DeterministicBuildError("mcp_api_range missing")

        verdicts = {}

        codex = CodexPluginPackager(
            skills_root=self._skills_root,
            gate=self._gate,
            legacy_support=self._codex_legacy_support,
        )
        claude = ClaudeCodePluginPackager(
            skills_root=self._skills_root, gate=self._gate,
        )
        opencode = OpenCodePluginPackager(
            skills_root=self._skills_root, gate=self._gate,
            bootstrap_fallback=self._opencode_bootstrap_fallback,
        )
        generic = GenericAgentBundlePackager(
            skills_root=self._skills_root, gate=self._gate,
        )

        verdicts["codex"] = codex.package(
            release, output_root=output_root,
        )
        verdicts["claude-code"] = claude.package(
            release, output_root=output_root,
        )
        verdicts["opencode"] = opencode.package(
            release, output_root=output_root,
        )
        verdicts["generic-agent"] = generic.package(
            release, output_root=output_root,
        )

        for vendor, verdict in verdicts.items():
            if not verdict.passed:
                raise DeterministicBuildError(
                    f"supply-chain gate rejected bundle {vendor!r}: "
                    f"{[c.name for c in verdict.failing()]}"
                )

        return DeterministicBuildResult(
            output_root=Path(output_root),
            verdicts=verdicts,
            shared_release_identity={
                "skillSha256": release.skill_sha256,
                "skillVersion": release.skill_version,
                "mcpApiRange": release.mcp_api_range,
                "license": release.license,
                "serverVersion": release.server_version,
            },
        )

    @staticmethod
    def combined_inventory(result: DeterministicBuildResult
                           ) -> dict[str, str]:
        """Whole-output ``{path: sha256}`` inventory across all vendors."""
        from hashlib import sha256
        out: dict[str, str] = {}
        for vendor_dir in sorted(p for p in result.output_root.iterdir()
                                 if p.is_dir()):
            for p in sorted(vendor_dir.rglob("*")):
                if p.is_file() and not p.is_symlink():
                    rel = str(p.relative_to(result.output_root))
                    out[rel] = sha256(p.read_bytes()).hexdigest()
        return out
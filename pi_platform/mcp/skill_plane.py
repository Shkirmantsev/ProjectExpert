"""Phase 6 §38 skill distribution plane.

Exposes the canonical Agent Skill package through the MCP
``resources`` plane under the documented URI namespace:

* ``project-intelligence://distribution/manifest``
* ``project-intelligence://skills/index``
* ``project-intelligence://skills/<name>/<version>/SKILL.md``
* ``project-intelligence://skills/<name>/<version>/references/...``
* ``project-intelligence://skills/<name>/<version>/assets/...``

Every resource is content-addressed; two consecutive reads of
the same URI return byte-identical bytes. The manifest carries
the documented fields including ``distributionSchemaVersion``
(an identifier, not semver).

Resource handlers are pure functions so they can be tested
without the MCP SDK.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence


__all__ = [
    "DISTRIBUTION_SCHEMA_VERSION",
    "SkillDistributionPlane",
    "SkillDistributionError",
]


log = logging.getLogger(__name__)


DISTRIBUTION_SCHEMA_VERSION = "1"


class SkillDistributionError(RuntimeError):
    """Raised when a resource cannot be served."""


@dataclass(frozen=True)
class _DistributionManifest:
    platformVersion: str
    mcpApiVersion: str
    knowledgeSchemaVersion: str
    distributionSchemaVersion: str = DISTRIBUTION_SCHEMA_VERSION
    skill: Mapping[str, str] = field(default_factory=dict)
    okf: Mapping[str, Sequence[str]] = field(default_factory=dict)
    agentAdapters: Mapping[str, str] = field(default_factory=dict)
    a2aAdapterVersion: Optional[str] = None
    agentAdapterVersion: Optional[str] = None
    runtimeIndexSchemaVersion: Optional[str] = None

    def as_dict(self) -> dict:
        out = {
            "platformVersion": self.platformVersion,
            "mcpApiVersion": self.mcpApiVersion,
            "knowledgeSchemaVersion": self.knowledgeSchemaVersion,
            "distributionSchemaVersion": self.distributionSchemaVersion,
            "skill": dict(self.skill),
            "okf": {
                "supported": list(self.okf.get("supported", ())),
            },
            "agentAdapters": dict(self.agentAdapters),
        }
        if self.a2aAdapterVersion is not None:
            out["a2aAdapterVersion"] = self.a2aAdapterVersion
        if self.agentAdapterVersion is not None:
            out["agentAdapterVersion"] = self.agentAdapterVersion
        if self.runtimeIndexSchemaVersion is not None:
            out["runtimeIndexSchemaVersion"] = (
                self.runtimeIndexSchemaVersion)
        return out


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SkillDistributionPlane:
    """§38 distribution plane.

    Reads the canonical skill package from the ``skills_root``
    and serves byte-identical content for any pinned version.
    The ``list_resources()`` and ``read_resource()`` methods are
    the deterministic surface the MCP server wires into the
    SDK ``resources/list`` and ``resources/read`` handlers.
    """

    def __init__(self, *, skills_root: Path,
                 platform_version: str = "0.8.0",
                 mcp_api_version: str = "1.3.0",
                 knowledge_schema_version: str = "0.7.0",
                 agent_adapters: Optional[Mapping[str, str]] = None,
                 a2a_adapter_version: Optional[str] = None,
                 agent_adapter_version: Optional[str] = None,
                 runtime_index_schema_version: Optional[str] = None):
        self._skills_root = Path(skills_root)
        if not self._skills_root.is_dir():
            raise SkillDistributionError(
                f"skills_root does not exist: {skills_root!r}"
            )
        self._platform_version = platform_version
        self._mcp_api_version = mcp_api_version
        self._knowledge_schema_version = knowledge_schema_version
        self._agent_adapters = dict(agent_adapters or {})
        self._a2a_adapter_version = a2a_adapter_version
        self._agent_adapter_version = agent_adapter_version
        self._runtime_index_schema_version = (
            runtime_index_schema_version)
        self._manifest = self._build_manifest()

    @property
    def skills_root(self) -> Path:
        return self._skills_root

    @property
    def distribution_schema_version(self) -> str:
        return DISTRIBUTION_SCHEMA_VERSION

    def manifest(self) -> Mapping[str, object]:
        return self._manifest.as_dict()

    def manifest_bytes(self) -> bytes:
        payload = self._manifest.as_dict()
        return json.dumps(payload, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")

    def _build_manifest(self) -> _DistributionManifest:
        skills_index: list[dict] = []
        for skill_dir in sorted(p for p in self._skills_root.iterdir()
                                if p.is_dir()):
            skill_name = skill_dir.name
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            sha = _sha256_file(skill_md)
            frontmatter = _parse_frontmatter(skill_md.read_text())
            version = frontmatter.get("version", "0.0.0")
            skills_index.append({
                "name": skill_name,
                "version": str(version),
                "sha256": sha,
            })
        if not skills_index:
            raise SkillDistributionError(
                f"no skill packages found under {self._skills_root}"
            )
        primary = skills_index[0]
        return _DistributionManifest(
            platformVersion=self._platform_version,
            mcpApiVersion=self._mcp_api_version,
            knowledgeSchemaVersion=self._knowledge_schema_version,
            skill={
                "name": primary["name"],
                    "version": primary["version"],
                    "sha256": primary["sha256"],
                },
            okf={"supported": ["0.2"]},
            agentAdapters=self._agent_adapters,
            a2aAdapterVersion=self._a2a_adapter_version,
            agentAdapterVersion=self._agent_adapter_version,
            runtimeIndexSchemaVersion=self._runtime_index_schema_version,
        )

    def list_resources(self) -> tuple[str, ...]:
        prefix = "project-intelligence://"
        out = [prefix + "distribution/manifest",
               prefix + "skills/index"]
        for skill_dir in sorted(p for p in self._skills_root.iterdir()
                                if p.is_dir()):
            skill_name = skill_dir.name
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            frontmatter = _parse_frontmatter(skill_md.read_text())
            version = str(frontmatter.get("version", "0.0.0"))
            out.append(f"{prefix}skills/{skill_name}/{version}/SKILL.md")
            for ref_dir in (skill_dir / "references",):
                if not ref_dir.is_dir():
                    continue
                for ref in sorted(p for p in ref_dir.iterdir()
                                  if p.is_file()):
                    out.append(
                        f"{prefix}skills/{skill_name}/{version}/references/"
                        f"{ref.name}"
                    )
            assets_dir = skill_dir / "assets"
            if assets_dir.is_dir():
                for asset in sorted(p for p in assets_dir.iterdir()
                                    if p.is_file()):
                    out.append(
                        f"{prefix}skills/{skill_name}/{version}/assets/"
                        f"{asset.name}"
                    )
        return tuple(out)

    def read_resource(self, uri: str) -> bytes:
        if not uri.startswith("project-intelligence://"):
            raise SkillDistributionError(
                f"unsupported URI scheme: {uri!r}"
            )
        path = uri[len("project-intelligence://"):]
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] == "distribution" and \
                parts[1] == "manifest":
            return self.manifest_bytes()
        if len(parts) >= 2 and parts[0] == "skills" and parts[1] == "index":
            return self._skills_index_bytes()
        if len(parts) >= 4 and parts[0] == "skills":
            skill_name = parts[1]
            version = parts[2]
            tail = parts[3:]
            skill_dir = self._skills_root / skill_name
            if not skill_dir.is_dir():
                raise SkillDistributionError(
                    f"unknown skill: {skill_name!r}"
                )
            relative = Path(*tail) if tail else Path("SKILL.md")
            target = skill_dir / relative
            if not target.is_file():
                raise SkillDistributionError(
                    f"resource not found: {uri!r}"
                )
            # Refuse to escape the skill dir; refuse symlinks.
            try:
                target.resolve().relative_to(skill_dir.resolve())
            except ValueError as exc:
                raise SkillDistributionError(
                    f"resource escapes skill directory: {uri!r}"
                ) from exc
            if target.is_symlink():
                raise SkillDistributionError(
                    f"refusing to serve symlink: {uri!r}"
                )
            frontmatter = _parse_frontmatter(
                (skill_dir / "SKILL.md").read_text())
            pinned_version = str(frontmatter.get("version", "0.0.0"))
            if pinned_version != version:
                raise SkillDistributionError(
                    f"resource pinned at version {pinned_version!r}; "
                    f"requested {version!r}"
                )
            return target.read_bytes()
        raise SkillDistributionError(f"unsupported URI: {uri!r}")

    def _skills_index_bytes(self) -> bytes:
        index: list[dict] = []
        for skill_dir in sorted(p for p in self._skills_root.iterdir()
                                if p.is_dir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            frontmatter = _parse_frontmatter(skill_md.read_text())
            index.append({
                "name": skill_dir.name,
                "version": str(frontmatter.get("version", "0.0.0")),
                "sha256": _sha256_file(skill_md),
            })
        return json.dumps({"skills": index},
                          sort_keys=True, separators=(",", ":")
                          ).encode("utf-8")


def _parse_frontmatter(markdown: bytes | str) -> Mapping[str, object]:
    text = markdown.decode("utf-8") if isinstance(markdown, bytes) else markdown
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm = text[3:end].strip()
    out: dict[str, object] = {}
    current_key: Optional[str] = None
    for line in fm.splitlines():
        if line.startswith("  - "):
            if current_key is not None and current_key in out:
                if isinstance(out[current_key], list):
                    out[current_key].append(line[4:].strip())
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            value = value.strip()
            if value == "":
                out[key.strip()] = []
                current_key = key.strip()
            else:
                out[key.strip()] = _coerce(value)
                current_key = key.strip()
    return out


def _coerce(text: str) -> object:
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("\"'") for item in inner.split(",")]
    if text.startswith("\"") and text.endswith("\""):
        return text[1:-1]
    return text
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

import copy
import hashlib
import json
import logging
import mimetypes
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence
from urllib.parse import quote


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
        self._skill_entries, self._skill_files = self._snapshot_skills()

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
            version = _skill_version(frontmatter)
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

    def _snapshot_skills(self) -> tuple[dict, dict]:
        """Freeze manifests and bytes together for the lifetime of this server."""
        entries, files = {}, {}
        for skill_dir in sorted(self._skills_root.iterdir()):
            if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").is_file():
                continue
            if skill_dir.is_symlink():
                raise SkillDistributionError("symlinked skill directory")
            frontmatter = _extension_frontmatter((skill_dir / "SKILL.md").read_bytes())
            name = frontmatter.get("name")
            if (name != skill_dir.name or not isinstance(name, str)
                    or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
                    or len(name) > 64
                    or not isinstance(frontmatter.get("description"), str)
                    or not frontmatter["description"].strip()):
                raise SkillDistributionError("invalid skill name or description")
            resources, total = [], 0
            for path in sorted(skill_dir.rglob("*")):
                if path.is_symlink():
                    raise SkillDistributionError("symlink in skill package")
                if not path.is_file():
                    continue
                path.resolve().relative_to(skill_dir.resolve())
                total += path.stat().st_size
                if len(resources) >= 512 or total > 16 * 1024 * 1024:
                    raise SkillDistributionError("skill exceeds SEP-2640 package limits")
                raw = path.read_bytes()
                uri = f"skill://{name}/" + quote(path.relative_to(skill_dir).as_posix(), safe="/")
                files[uri] = raw
                resources.append({"uri": uri, "digest": "sha256:" + _sha256_bytes(raw),
                                  "size": len(raw)})
            uri = f"skill://{name}/SKILL.md"
            entries[uri] = {"uri": uri, "frontmatter": dict(frontmatter), "resources": resources}
        return entries, files

    def list_skills(self, cursor: object = None) -> list[dict]:
        # The bundled catalog fits one complete page; no continuation is issued.
        if cursor is not None:
            raise SkillDistributionError("unknown skills cursor")
        return copy.deepcopy(list(self._skill_entries.values()))

    def get_skill(self, uri: str) -> dict:
        if not isinstance(uri, str) or uri not in self._skill_entries:
            raise SkillDistributionError("unknown skill URI")
        return copy.deepcopy(self._skill_entries[uri])

    def resource_metadata(self, uri: str) -> dict:
        metadata = {"uri": uri, "name": uri.rsplit("/", 1)[-1],
                    "mimeType": mimetypes.guess_type(uri)[0] or "application/octet-stream"}
        if uri.endswith(".md"):
            metadata["mimeType"] = "text/markdown"
        if uri in self._skill_entries:
            fm = self._skill_entries[uri]["frontmatter"]
            metadata.update(name=fm["name"], description=fm["description"])
        return metadata

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
            version = str(_skill_version(frontmatter))
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
        return tuple(out) + tuple(self._skill_files)

    def read_resource(self, uri: str) -> bytes:
        if uri.startswith("skill://"):
            if uri not in self._skill_files:
                raise SkillDistributionError("unknown skill resource URI")
            return self._skill_files[uri]
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
            pinned_version = str(_skill_version(frontmatter))
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
                "version": str(_skill_version(frontmatter)),
                "sha256": _sha256_file(skill_md),
            })
        return json.dumps({"skills": index},
                          sort_keys=True, separators=(",", ":")
                          ).encode("utf-8")


def _skill_version(frontmatter: Mapping[str, object]) -> str:
    metadata = frontmatter.get("metadata", {})
    return str(frontmatter.get("version") or
               (metadata.get("version") if isinstance(metadata, Mapping) else None) or "0.0.0")


def _extension_frontmatter(raw: bytes) -> Mapping[str, object]:
    """Parse complete metadata; the stdlib subset covers our shipped skill.

    Arbitrary YAML belongs to the optional YAML adapter. Fail closed rather
    than flattening or silently dropping fields when it is unavailable.
    """
    text = raw.decode("utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        raise SkillDistributionError("skill requires YAML frontmatter")
    try:
        import yaml
    except ImportError:
        result = {}
        stack = [(-1, result)]
        mappings = [result]
        for line in match[1].splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "\t" in line[:len(line) - len(line.lstrip())]:
                raise SkillDistributionError("tabs are not allowed in YAML indentation")
            key, separator, value = stripped.partition(":")
            if not separator or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
                raise SkillDistributionError("this frontmatter requires optional PyYAML")
            indent = len(line) - len(line.lstrip(" "))
            while stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1]
            if key in parent:
                raise SkillDistributionError("duplicate frontmatter key")
            value = value.strip()
            if not value:
                parent[key] = {}
                mappings.append(parent[key])
                stack.append((indent, parent[key]))
            elif value.startswith('"'):
                parent[key] = json.loads(value)
            elif value.startswith("'") and value.endswith("'"):
                parent[key] = value[1:-1].replace("''", "'")
            elif re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
                parent[key] = value
            elif (value[0] in "[{>|&*!\'" or " #" in value or ": " in value
                  or value.lower() in {"true", "false", "null", "yes", "no", "on", "off", "~", ".nan", ".inf", "-.inf", "+.inf"}
                  or re.match(r"^[+-]?[0-9]", value)):
                raise SkillDistributionError("this frontmatter requires optional PyYAML")
            else:
                parent[key] = value
        if any(not mapping for mapping in mappings):
            raise SkillDistributionError("empty YAML values require optional PyYAML")
    else:
        result = yaml.safe_load(match[1])
    if not isinstance(result, dict):
        raise SkillDistributionError("skill frontmatter must be a mapping")
    # Ensure metadata has a faithful JSON representation before publishing it.
    try:
        if json.loads(json.dumps(result, allow_nan=False)) != result:
            raise ValueError("frontmatter mapping keys must be strings")
    except (TypeError, ValueError) as exc:
        raise SkillDistributionError("frontmatter must contain JSON-compatible values") from exc
    return result


def _parse_frontmatter(markdown: bytes | str) -> Mapping[str, object]:
    raw = markdown.encode("utf-8") if isinstance(markdown, str) else markdown
    return _extension_frontmatter(raw)

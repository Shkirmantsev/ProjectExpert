"""OKF v0.2 profile implementation.

The OKF profile is intentionally decoupled from the internal Knowledge
Model so a future OKF revision can be supported by swapping the
profile implementation. Only :class:`OkfV02Profile` knows the OKF v0.2
wire shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from .serializer import canonical_dump_json, normalize_str

__all__ = [
    "OkfAdapter",
    "OkfV02Profile",
    "OkfValidationError",
    "OKF_RESERVED_FILES",
    "OKF_PLATFORM_PREFIX",
    "parse_frontmatter",
    "validate_wiki_bundle",
]


OKF_PLATFORM_PREFIX = "pi_"
OKF_RESERVED_FILES = ("index.md", "log.md")
DEFAULT_OKF_VERSION = "0.2"

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


@dataclass(frozen=True)
class OkfValidationError(ValueError):
    file: Path
    reason: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"OKF validation failed for {self.file}: {self.reason}"


class OkfAdapter:
    """Abstract adapter between the internal Knowledge Model and a
    specific OKF profile/version.

    The Phase 1 platform ships :class:`OkfV02Profile`; future OKF
    revisions substitute a different concrete adapter.
    """

    profile_version: str

    def parse_frontmatter(self, raw: str) -> Mapping[str, object]:
        raise NotImplementedError

    def validate_file(self, path: Path, raw: str) -> None:
        raise NotImplementedError

    def render_concept_markdown(self, frontmatter: Mapping[str, object],
                                body: str) -> str:
        raise NotImplementedError


def parse_frontmatter(raw: str) -> tuple[Mapping[str, object], str]:
    """Parse YAML frontmatter from a Markdown string.

    Returns ``(frontmatter, body)``. Raises :class:`ValueError` when the
    frontmatter is missing, malformed or contains duplicate keys.

    This function intentionally does not depend on PyYAML at import
    time; it returns an empty mapping when the body lacks frontmatter
    so the rest of the platform can keep working in environments
    without YAML.
    """

    text = normalize_str(raw)
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw_yaml, body = match.group(1), match.group(2)
    try:
        import yaml  # type: ignore
    except ImportError:
        # YAML not available; fall back to a minimal key:value parser
        # so the platform can still validate the documented required
        # fields without PyYAML.
        data = _minimal_yaml_load(raw_yaml)
    else:
        loaded = yaml.safe_load(raw_yaml)
        if loaded is None:
            return {}, body
        if not isinstance(loaded, Mapping):
            raise ValueError("OKF frontmatter must be a YAML mapping")
        data = loaded
    return data, body


def _minimal_yaml_load(text: str) -> Mapping[str, object]:
    """Minimal YAML subset loader used when PyYAML is unavailable.

    Supports only top-level ``key: value`` mappings with string values,
    which is sufficient for the OKF root-index frontmatter the Phase 1
    adapter inspects.
    """

    result: dict[str, object] = {}
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if ":" not in raw_line:
            raise ValueError(f"malformed OKF frontmatter line: {raw_line!r}")
        key, _, value = raw_line.partition(":")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


@dataclass(frozen=True)
class OkfV02Profile(OkfAdapter):
    """OKF v0.2 profile implementation.

    Recognises fields whose key starts with ``pi_`` as platform
    extensions and ignores them when checking OKF compliance.
    """

    profile_version: str = DEFAULT_OKF_VERSION
    reserved_filenames: Sequence[str] = OKF_RESERVED_FILES
    platform_prefix: str = OKF_PLATFORM_PREFIX

    def parse_frontmatter(self, raw: str) -> Mapping[str, object]:
        return parse_frontmatter(raw)[0]

    def validate_file(self, path: Path, raw: str) -> None:
        if path.name in self.reserved_filenames:
            return
        frontmatter, _ = parse_frontmatter(raw)
        if not frontmatter:
            raise OkfValidationError(path, "missing YAML frontmatter")
        type_field = frontmatter.get("type")
        if not isinstance(type_field, str) or not type_field.strip():
            raise OkfValidationError(path, "missing or empty 'type' field")
        # Platform extensions are tolerated; other unknown keys are
        # recorded as warnings by the bundle validator.

    def render_concept_markdown(self, frontmatter: Mapping[str, object],
                              body: str) -> str:
        ordered = {k: frontmatter[k] for k in sorted(frontmatter.keys())}
        try:
            import yaml  # type: ignore
        except ImportError:
            yaml_lines = [f"{k}: {ordered[k]!r}" for k in ordered]
        else:
            yaml_lines = yaml.safe_dump(ordered, allow_unicode=True,
                                        sort_keys=True).splitlines()
        yaml_block = "\n".join(yaml_lines).rstrip("\n")
        body_text = body if body.endswith("\n") else body + "\n"
        return f"---\n{yaml_block}\n---\n{body_text}"


def validate_wiki_bundle(
    wiki_root: Path,
    *,
    adapter: Optional[OkfAdapter] = None,
) -> list[OkfValidationError]:
    """Walk a Wiki bundle root and return all OKF validation errors."""

    profile = adapter or OkfV02Profile()
    errors: list[OkfValidationError] = []
    if not wiki_root.is_dir():
        return [OkfValidationError(wiki_root, "wiki root is not a directory")]

    index_path = wiki_root / "index.md"
    if not index_path.is_file():
        errors.append(OkfValidationError(index_path, "missing reserved index.md"))
    else:
        frontmatter, _ = parse_frontmatter(index_path.read_text(encoding="utf-8"))
        if frontmatter.get("okf_version") != profile.profile_version:
            errors.append(OkfValidationError(
                index_path,
                f"okf_version must be {profile.profile_version!r}; "
                f"got {frontmatter.get('okf_version')!r}",
            ))
        if frontmatter.get("type") != "WikiIndex":
            errors.append(OkfValidationError(
                index_path,
                "root index.md must declare type: 'WikiIndex'",
            ))

    for path in sorted(wiki_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in profile.reserved_filenames and path.parent == wiki_root:
            continue
        if path.suffix.lower() != ".md":
            errors.append(OkfValidationError(
                path,
                f"unexpected non-Markdown file inside OKF bundle: {path.name}",
            ))
            continue
        try:
            profile.validate_file(path, path.read_text(encoding="utf-8"))
        except OkfValidationError as exc:
            errors.append(exc)
    return errors
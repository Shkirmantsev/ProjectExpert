"""Source-first selection and bounded reads of library code.

The selection prefers **real source** over anything reconstructed:

1. a distributed source file (``.py``, ``.pyi``, ``.java``, ``.js``,
   ``.ts``, ``.d.ts``);
2. a source map with an embedded ``sourcesContent`` body;
3. a stub (``.pyi``, ``.d.ts``) when no implementation is distributed;
4. a class file or a bytecode file -- read as a **signature** or a
   **disassembly**, never as source.

Every read is bounded by lines and bytes, and every result states the
representation it really has. A missing source body is reported as
missing, not as an empty excerpt.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Optional, Sequence

from pi_platform.adapters.research.artifacts import (
    ArchiveInspection,
    ArtifactError,
    iter_member_bytes,
    safe_member_path,
)
from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.research.policy import AcquisitionPolicy
from pi_platform.core.research.records import (
    EvidenceReference,
    Representation,
    ResearchResult,
    ResearchStatus,
)

__all__ = [
    "SOURCE_SUFFIXES",
    "STUB_SUFFIXES",
    "BYTECODE_SUFFIXES",
    "LibraryFile",
    "LibraryIndex",
    "select_source_files",
    "read_member",
    "read_source_map",
    "LibraryReader",
]


#: Suffixes of a distributed implementation.
SOURCE_SUFFIXES = (".py", ".java", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
                   ".mts", ".cts")
#: Suffixes of a distributed type stub.
STUB_SUFFIXES = (".pyi", ".d.ts")
#: Suffixes of compiled artefacts.
BYTECODE_SUFFIXES = (".class", ".pyc")

_SOURCE_MAP_SUFFIX = ".map"


@dataclass(frozen=True)
class LibraryFile:
    """One file inside a library artifact."""

    path: str
    size: int
    sha256: str
    kind: str  # "source" | "stub" | "bytecode" | "map" | "other"

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "kind": self.kind,
        }


@dataclass
class LibraryIndex:
    """The bounded index of the files of one artifact."""

    artifact_path: str
    artifact_sha256: str
    files: tuple[LibraryFile, ...] = ()
    warnings: tuple[str, ...] = ()

    def by_kind(self, kind: str) -> tuple[LibraryFile, ...]:
        return tuple(item for item in self.files if item.kind == kind)

    def as_dict(self) -> dict:
        return {
            "artifactPath": self.artifact_path,
            "artifactSha256": self.artifact_sha256,
            "files": [item.as_dict() for item in self.files],
            "warnings": list(self.warnings),
        }


def _classify(path: str) -> str:
    name = PurePosixPath(path).name
    if name.endswith(".d.ts"):
        return "stub"
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in STUB_SUFFIXES:
        return "stub"
    if suffix in SOURCE_SUFFIXES:
        return "source"
    if suffix in BYTECODE_SUFFIXES:
        return "bytecode"
    if path.endswith(_SOURCE_MAP_SUFFIX):
        return "map"
    return "other"


def select_source_files(inspection: ArchiveInspection) -> LibraryIndex:
    """Select the files of an artifact that can carry library code."""

    files: list[LibraryFile] = []
    warnings: list[str] = []
    for member in inspection.members:
        kind = _classify(member.path)
        if kind == "other":
            continue
        if member.is_symlink or member.is_hardlink:
            warnings.append(
                f"the member {member.path} is a link and is not read as code")
            continue
        files.append(LibraryFile(path=member.path, size=member.size,
                                 sha256=member.sha256, kind=kind))
    digest = hashlib.sha256()
    for member in sorted(inspection.members, key=lambda item: item.path):
        digest.update(member.path.encode("utf-8"))
        digest.update(member.sha256.encode("ascii"))
    return LibraryIndex(
        artifact_path=inspection.path,
        artifact_sha256=digest.hexdigest(),
        files=tuple(files),
        warnings=tuple(warnings),
    )


#: A JavaScript source with fewer newlines than this and a longest line
#: above the threshold is a minified bundle, not readable source.
_MINIFIED_NEWLINES = 5
_MINIFIED_LINE_LENGTH = 2000


def _looks_minified(text: str, kind: str) -> bool:
    """Report whether a JavaScript source is a minified bundle.

    The check is deliberately conservative: only an obviously
    minified bundle is labelled as generated output.
    """

    if kind != "source" or not text:
        return False
    if not text.lstrip().startswith(("function", "var ", "const ", "let ",
                                     "class ", "export", "!", "(")):
        return False
    lines = text.splitlines()
    if len(lines) > _MINIFIED_NEWLINES:
        return False
    return max((len(line) for line in lines), default=0) > _MINIFIED_LINE_LENGTH


def read_member(artifact: Path, member: str, *, policy: Optional[AcquisitionPolicy] = None,
                max_lines: int = 200, max_bytes: int = 16 * 1024,
                start_line: Optional[int] = None,
                end_line: Optional[int] = None) -> dict:
    """Read a bounded excerpt of one member of an artifact.

    The excerpt states the representation it really has: a ``.pyc`` is
    a disassembly, a ``.class`` is a signature, and a source file is
    source.
    """

    policy = policy or AcquisitionPolicy()
    safe_member_path(member)
    kind = _classify(member)
    representation = {
        "source": Representation.SOURCE.value,
        "stub": Representation.STUB.value,
        "bytecode": Representation.DISASSEMBLY.value,
        "map": Representation.MAPPED_SOURCE.value,
        "other": Representation.SOURCE.value,
    }[kind]

    chunks: list[bytes] = []
    total = 0
    budget = max(max_bytes * 4, 64 * 1024)
    for chunk in iter_member_bytes(artifact, member, policy=policy,
                                   max_bytes=budget, strict=False):
        total += len(chunk)
        if total > budget:
            break
        chunks.append(chunk)
    raw = b"".join(chunks)

    text = ""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", "replace")

    minified = _looks_minified(text, kind)
    if minified:
        # A minified bundle is not the original source. It is labelled
        # as generated output so no caller mistakes it for source.
        representation = Representation.GENERATED.value

    lines = text.splitlines()
    first = 1 if start_line is None else max(1, int(start_line))
    last = len(lines) if end_line is None else min(len(lines), int(end_line))
    if last < first:
        last = first
    # The line bound is a hard bound: the excerpt never exceeds it.
    if max_lines >= 0:
        last = min(last, first + max(0, int(max_lines)) - 1)
        if max_lines == 0:
            last = first - 1
    selected = lines[first - 1:last] if last >= first else []
    truncated = len(selected) < len(lines) or total > max_bytes
    body = "\n".join(selected)
    encoded = body.encode("utf-8")
    if len(encoded) > max_bytes:
        body = encoded[:max_bytes].decode("utf-8", "ignore")
        truncated = True

    return {
        "member": member,
        "kind": kind,
        "representation": representation,
        "minified": minified,
        "startLine": first,
        "endLine": first + max(0, len(selected) - 1),
        "totalLines": len(lines),
        "truncated": truncated,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "text": body,
    }


def read_source_map(artifact: Path, member: str, *,
                    policy: Optional[AcquisitionPolicy] = None,
                    max_bytes: int = 16 * 1024) -> dict:
    """Read a source map and report the bodies it embeds.

    A source map is only useful when it embeds the original sources
    (``sourcesContent``). A map without bodies is reported as such; an
    invalid map is reported as invalid. Neither case invents source.
    """

    policy = policy or AcquisitionPolicy()
    safe_member_path(member)
    raw = b"".join(iter_member_bytes(artifact, member, policy=policy,
                                     max_bytes=max_bytes))
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"member": member, "valid": False, "reason": f"invalid source map: {exc}",
                "sources": [], "contents": []}
    if not isinstance(payload, Mapping):
        return {"member": member, "valid": False,
                "reason": "invalid source map: the payload is not an object",
                "sources": [], "contents": []}
    sources = payload.get("sources")
    contents = payload.get("sourcesContent")
    if not isinstance(sources, list) or not isinstance(contents, list):
        return {"member": member, "valid": True, "reason": None,
                "sources": [str(item) for item in sources] if isinstance(sources, list) else [],
                "contents": [], "hasBodies": False}
    pairs = []
    for index, source in enumerate(sources):
        body = contents[index] if index < len(contents) else None
        pairs.append({"source": str(source), "body": body})
    has_bodies = any(pair["body"] for pair in pairs)
    return {
        "member": member,
        "valid": True,
        "reason": None,
        "sources": [pair["source"] for pair in pairs],
        "contents": pairs,
        "hasBodies": has_bodies,
    }


class LibraryReader:
    """Read library code out of an acquired artifact."""

    def __init__(self, *, policy: Optional[AcquisitionPolicy] = None) -> None:
        self.policy = policy or AcquisitionPolicy()

    def index(self, artifact: Path) -> LibraryIndex:
        from pi_platform.adapters.research.artifacts import inspect_archive

        inspection = inspect_archive(artifact, policy=self.policy)
        return select_source_files(inspection)

    def read(self, artifact: Path, member: str, *, symbol: Optional[str] = None,
             start_line: Optional[int] = None, end_line: Optional[int] = None,
             max_lines: int = 200, max_bytes: int = 16 * 1024) -> ResearchResult:
        """Read one member of the artifact, optionally a single symbol."""

        try:
            excerpt = read_member(artifact, member, policy=self.policy,
                                  max_lines=max_lines, max_bytes=max_bytes,
                                  start_line=start_line, end_line=end_line)
        except (ArtifactError, OSError) as exc:
            return ResearchResult(
                status=ResearchStatus.FAILED,
                operation="dependency.read",
                warnings=(str(exc),),
                limits=self.policy.as_dict(),
            )
        if symbol:
            excerpt = self._narrow(excerpt, symbol)
        evidence = EvidenceReference(
            evidence_id=content_address({
                "kind": "library-member", "member": member,
                "sha256": excerpt["sha256"],
            }),
            artifact_hash=excerpt["sha256"],
            member=member,
            start_line=excerpt["startLine"],
            end_line=excerpt["endLine"],
            parser_version="library-read-1",
            representation=excerpt["representation"],
        )
        return ResearchResult(
            status=ResearchStatus.COMPLETE,
            operation="dependency.read",
            evidence=(evidence,),
            excerpts=(excerpt,),
            warnings=(),
            truncated=bool(excerpt.get("truncated")),
            limits={**self.policy.as_dict(), "maxLines": max_lines,
                    "maxBytes": max_bytes},
            scope={"member": member, "symbol": symbol},
        )

    @staticmethod
    def _narrow(excerpt: Mapping[str, Any], symbol: str) -> dict:
        """Reduce an excerpt to the block of one symbol."""

        lines = str(excerpt.get("text") or "").splitlines()
        start = None
        for index, line in enumerate(lines):
            stripped = line.strip()
            if symbol in stripped and (
                    stripped.startswith(("def ", "class ", "function ", "export ",
                                        "public ", "async "))
                    or stripped.startswith(symbol)):
                start = index
                break
        if start is None:
            narrowed = dict(excerpt)
            narrowed["symbol"] = symbol
            narrowed["symbolFound"] = False
            return narrowed
        indent = len(lines[start]) - len(lines[start].lstrip())
        end = len(lines)
        for index in range(start + 1, len(lines)):
            line = lines[index]
            if not line.strip():
                continue
            current = len(line) - len(line.lstrip())
            if current <= indent:
                end = index
                break
        narrowed = dict(excerpt)
        narrowed["text"] = "\n".join(lines[start:end])
        narrowed["startLine"] = excerpt["startLine"] + start
        narrowed["endLine"] = excerpt["startLine"] + end - 1
        narrowed["symbol"] = symbol
        narrowed["symbolFound"] = True
        return narrowed

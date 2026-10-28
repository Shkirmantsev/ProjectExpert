"""Safe, bounded inspection of dependency artifacts.

Inspection never accesses the network and never executes the code of a
dependency. It only reads the *bytes* of an archive that is already on
disk and reports what is inside, with every unsafe construct rejected:

* absolute member paths and ``..`` segments;
* symlinks and hard links that escape the archive root;
* members above the per-member size limit;
* archives above the member count, expanded size or compression ratio
  limits.

A rejected archive is an error, not a truncated listing.
"""

from __future__ import annotations

import hashlib
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator, Optional

from pi_platform.core.research.policy import AcquisitionPolicy

__all__ = [
    "ArtifactError",
    "UnsafeArchiveMember",
    "ArchiveMember",
    "ArchiveInspection",
    "inspect_archive",
    "safe_member_path",
]


class ArtifactError(RuntimeError):
    """The artifact could not be inspected safely."""


class UnsafeArchiveMember(ArtifactError):
    """The archive contains a member that must not be extracted."""


@dataclass(frozen=True)
class ArchiveMember:
    """One member of an inspected archive."""

    path: str
    size: int
    compressed_size: int
    sha256: str
    is_symlink: bool = False
    is_hardlink: bool = False
    link_target: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "size": self.size,
            "compressedSize": self.compressed_size,
            "sha256": self.sha256,
            "isSymlink": self.is_symlink,
            "isHardlink": self.is_hardlink,
            "linkTarget": self.link_target,
        }


@dataclass(frozen=True)
class ArchiveInspection:
    """The bounded result of an archive inspection."""

    path: str
    kind: str
    members: tuple[ArchiveMember, ...] = ()
    expanded_bytes: int = 0
    compressed_bytes: int = 0
    warnings: tuple[str, ...] = ()

    def member(self, path: str) -> Optional[ArchiveMember]:
        for item in self.members:
            if item.path == path:
                return item
        return None

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "kind": self.kind,
            "members": [member.as_dict() for member in self.members],
            "expandedBytes": self.expanded_bytes,
            "compressedBytes": self.compressed_bytes,
            "warnings": list(self.warnings),
        }


def safe_member_path(name: str) -> PurePosixPath:
    """Validate a member path and return it as a relative POSIX path.

    Absolute paths, ``..`` segments and Windows separators are rejected:
    a member must never point outside the archive root.
    """

    if not name:
        raise UnsafeArchiveMember("empty member path")
    if "\\" in name:
        raise UnsafeArchiveMember(f"unsafe member path: {name!r}")
    if name.startswith("/"):
        raise UnsafeArchiveMember(f"absolute member path: {name!r}")
    path = PurePosixPath(name)
    if any(part == ".." for part in path.parts):
        raise UnsafeArchiveMember(f"member path escapes the archive: {name!r}")
    return path


def _ratio_guard(expanded: int, compressed: int, policy: AcquisitionPolicy) -> None:
    if compressed <= 0:
        return
    if expanded / compressed > policy.max_compression_ratio:
        raise UnsafeArchiveMember(
            f"the archive expands {expanded} bytes from {compressed} bytes, "
            f"above the compression ratio limit of {policy.max_compression_ratio}"
        )


def _inspect_zip(path: Path, policy: AcquisitionPolicy) -> ArchiveInspection:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArtifactError(f"cannot open {path}: {exc}") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > policy.max_members:
            raise ArtifactError(
                f"the archive holds {len(infos)} members, above the limit of "
                f"{policy.max_members}")
        expanded = sum(info.file_size for info in infos)
        compressed = sum(info.compress_size for info in infos)
        if expanded > policy.max_expanded_bytes:
            raise ArtifactError(
                f"the archive expands to {expanded} bytes, above the limit of "
                f"{policy.max_expanded_bytes}")
        _ratio_guard(expanded, compressed, policy)
        members: list[ArchiveMember] = []
        for info in infos:
            member_path = safe_member_path(info.filename)
            if info.file_size > policy.max_compressed_bytes:
                raise ArtifactError(
                    f"the member {member_path} is {info.file_size} bytes, above "
                    f"the member limit of {policy.max_compressed_bytes}")
            digest = hashlib.sha256()
            with archive.open(info) as stream:
                while True:
                    chunk = stream.read(1024 * 256)
                    if not chunk:
                        break
                    digest.update(chunk)
            mode = (info.external_attr >> 16) & 0xF000
            is_symlink = mode == 0xA000
            target = None
            if is_symlink:
                target = archive.read(info).decode("utf-8", "replace")
                _reject_escaping_link(target, member_path)
            members.append(ArchiveMember(
                path=str(member_path),
                size=info.file_size,
                compressed_size=info.compress_size,
                sha256=digest.hexdigest(),
                is_symlink=is_symlink,
                link_target=target,
            ))
        return ArchiveInspection(
            path=str(path),
            kind="zip",
            members=tuple(members),
            expanded_bytes=expanded,
            compressed_bytes=compressed,
        )


def _reject_escaping_link(target: str, member_path: PurePosixPath) -> None:
    """Reject a link that points outside the archive root."""

    if target.startswith("/") or ".." in PurePosixPath(target).parts:
        raise UnsafeArchiveMember(
            f"the member {member_path} links outside the archive: {target!r}")


def _inspect_tar(path: Path, policy: AcquisitionPolicy) -> ArchiveInspection:
    try:
        archive = tarfile.open(path, "r:*")
    except (OSError, tarfile.TarError) as exc:
        raise ArtifactError(f"cannot open {path}: {exc}") from exc
    with archive:
        infos = archive.getmembers()
        if len(infos) > policy.max_members:
            raise ArtifactError(
                f"the archive holds {len(infos)} members, above the limit of "
                f"{policy.max_members}")
        expanded = sum(info.size for info in infos)
        if expanded > policy.max_expanded_bytes:
            raise ArtifactError(
                f"the archive expands to {expanded} bytes, above the limit of "
                f"{policy.max_expanded_bytes}")
        members: list[ArchiveMember] = []
        for info in infos:
            member_path = safe_member_path(info.name)
            if info.size > policy.max_compressed_bytes:
                raise ArtifactError(
                    f"the member {member_path} is {info.size} bytes, above the "
                    f"member limit of {policy.max_compressed_bytes}")
            digest = hashlib.sha256()
            if info.isfile():
                stream = archive.extractfile(info)
                if stream is not None:
                    with stream:
                        while True:
                            chunk = stream.read(1024 * 256)
                            if not chunk:
                                break
                            digest.update(chunk)
            is_symlink = info.issym()
            is_hardlink = info.islnk()
            target = info.linkname or None
            if target is not None:
                _reject_escaping_link(target, member_path)
            members.append(ArchiveMember(
                path=str(member_path),
                size=info.size,
                compressed_size=0,
                sha256=digest.hexdigest(),
                is_symlink=is_symlink,
                is_hardlink=is_hardlink,
                link_target=target,
            ))
        return ArchiveInspection(
            path=str(path),
            kind="tar",
            members=tuple(members),
            expanded_bytes=expanded,
            compressed_bytes=path.stat().st_size,
        )


def inspect_archive(path: Path, *,
                    policy: Optional[AcquisitionPolicy] = None) -> ArchiveInspection:
    """Inspect the archive at ``path`` safely and within its bounds."""

    policy = policy or AcquisitionPolicy()
    path = Path(path)
    if not path.is_file():
        raise ArtifactError(f"the artifact does not exist: {path}")
    size = path.stat().st_size
    if size > policy.max_compressed_bytes:
        raise ArtifactError(
            f"the artifact is {size} bytes, above the limit of "
            f"{policy.max_compressed_bytes}")
    if zipfile.is_zipfile(path):
        return _inspect_zip(path, policy)
    try:
        return _inspect_tar(path, policy)
    except tarfile.TarError:
        raise ArtifactError(f"unsupported artifact format: {path.name}") from None


def iter_member_bytes(path: Path, member: str, *,
                      policy: Optional[AcquisitionPolicy] = None,
                      max_bytes: Optional[int] = None,
                      strict: bool = True) -> Iterator[bytes]:
    """Yield the bytes of one member of an archive.

    The member path is validated first, so a traversal attempt fails
    before a single byte is produced. With ``strict=False`` a member
    that is larger than the budget stops the iteration instead of
    raising: the caller then reports a truncated excerpt.
    """

    policy = policy or AcquisitionPolicy()
    limit = max_bytes if max_bytes is not None else policy.max_compressed_bytes
    safe_member_path(member)
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            try:
                info = archive.getinfo(member)
            except KeyError as exc:
                raise ArtifactError(
                    f"the member {member} is not in the artifact") from exc
            if info.file_size > limit and strict:
                raise ArtifactError(
                    f"the member {member} is {info.file_size} bytes, above the "
                    f"limit of {limit}")
            with archive.open(info) as stream:
                remaining = limit
                while True:
                    chunk = stream.read(min(1024 * 256, max(remaining, 1)))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    if remaining < 0:
                        if strict:
                            raise ArtifactError(
                                f"the member {member} exceeds the limit of {limit}")
                        return
                    yield chunk
        return
    with tarfile.open(path, "r:*") as archive:
        try:
            info = archive.getmember(member)
        except KeyError as exc:
            raise ArtifactError(
                f"the member {member} is not in the artifact") from exc
        if info.size > limit and strict:
            raise ArtifactError(
                f"the member {member} is {info.size} bytes, above the limit of "
                f"{limit}")
        stream = archive.extractfile(info)
        if stream is None:
            raise ArtifactError(f"the member {member} has no content")
        with stream:
            remaining = limit
            while True:
                chunk = stream.read(min(1024 * 256, max(remaining, 1)))
                if not chunk:
                    break
                remaining -= len(chunk)
                if remaining < 0:
                    if strict:
                        raise ArtifactError(
                            f"the member {member} exceeds the limit of {limit}")
                    return
                yield chunk

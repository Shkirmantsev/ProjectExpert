"""Deterministic inbox scanning with explicit, serializable promotion policy."""

import hashlib
import logging
import fnmatch
import subprocess
from dataclasses import replace
from pathlib import Path
from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.canonical.value_types import (
    Metadata,
    Source,
    KnowledgeState,
    to_canonical_json,
)
from pi_platform.ports.ingest.local_source_inbox_scanner import (
    LocalSourceInboxContext,
    LocalSourceInboxReport,
    LocalSourceInboxScannerPort,
    SourcePromotionPolicy,
    UnknownSource,
    InvalidPolicy,
    PromotionDenied,
)

log = logging.getLogger(__name__)


class LocalSourceInboxScanner(LocalSourceInboxScannerPort):
    KNOWN_SUFFIXES = {
        ".md",
        ".markdown",
        ".txt",
        ".text",
        ".html",
        ".htm",
        ".java",
        ".jar",
        ".pom",
        ".xml",
        ".gradle",
        ".kts",
        ".pdf",
        ".yaml",
        ".yml",
        ".json",
        ".properties",
    }

    def __init__(self, cache=None):
        self.cache = cache
        self._previous = {}

    def scan(self, context):
        root = context.project_root.resolve()
        maximum = int(context.extra.get("max_source_bytes", 256 * 1024 * 1024))
        tracked = set(context.extra.get("tracked_paths", ()))
        repo = Path(context.extra.get("repository_root", root)).resolve()
        try:
            output = subprocess.run(
                ["git", "-C", str(repo), "ls-files", "-z"],
                capture_output=True,
                check=True,
                timeout=10,
            )
            index_paths = {
                str((repo / p.decode()).resolve())
                for p in output.stdout.split(b"\0")
                if p
            }
            head = subprocess.run(
                ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "-z", "HEAD"],
                capture_output=True,
                check=True,
                timeout=10,
            )
            head_paths = {
                str((repo / p.decode()).resolve())
                for p in head.stdout.split(b"\0")
                if p
            }
            tracked.update(index_paths & head_paths)
        except (OSError, subprocess.SubprocessError):
            pass
        sources, skipped, scanned, current = [], [], [], {}
        iterator = root.rglob("*") if context.recursive else root.glob("*")
        for path in sorted(iterator, key=lambda p: p.relative_to(root).as_posix()):
            if not path.is_file():
                continue
            if (
                ".git" in path.relative_to(root).parts
                or path.suffix.lower() not in self.KNOWN_SUFFIXES
            ):
                skipped.append(path)
                continue
            relative = path.relative_to(root)
            if (
                path.is_symlink()
                or str(path.resolve()) in tracked
                or relative.as_posix() in tracked
                or path.stat().st_size > maximum
            ):
                skipped.append(path)
                log.info(
                    "inbox skipped path=%s reason=tracked/symlink/size-limit", path
                )
                continue
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise UnknownSource(f"cannot read {path}: {exc}") from exc
            scanned.append(path)
            policy = self.resolve_policy(
                relative, context.default_policy, context.override_map
            )
            digest = hashlib.sha256(data).hexdigest()
            sid = content_address({"path": str(path)})
            source = Source(
                sid,
                str(path),
                self._family_for(path),
                digest,
                Metadata(
                    sid,
                    digest,
                    self._family_for(path),
                    sourcePath=str(path),
                    contentHash=digest,
                    policy=policy.value,
                    extensions={
                        "pi_processing_context": context.extra.get(
                            "processing_fingerprint", ""
                        )
                    },
                ),
            )
            current[str(path)] = source
            # Driver owns content/body reuse; scanner skips only explicitly completed source hashes.
            if self.cache is not None and self.cache.source_is_current(
                sid,
                digest,
                content_address(to_canonical_json(source.metadata).decode()),
            ):
                skipped.append(path)
                continue
            sources.append(source)
        previous = self._previous.get(str(root), {})
        deleted = tuple(sorted(s.id for p, s in previous.items() if p not in current))
        for sid in deleted:
            if self.cache is not None:
                self.cache.invalidate_source(sid)
            log.info("source deleted id=%s derived-state=stale", sid)
        self._previous[str(root)] = current
        return LocalSourceInboxReport(
            tuple(scanned),
            tuple(sources),
            tuple(skipped),
            (),
            deleted_source_ids=deleted,
        )

    def resolve_policy(self, source_path, default_policy, override_map):
        candidates = [
            (g, p)
            for g, p in override_map.items()
            if fnmatch.fnmatch(source_path.as_posix(), g)
        ]
        candidates.sort(key=lambda x: (-len(x[0]), x[0]))
        policy = candidates[0][1] if candidates else default_policy
        try:
            return SourcePromotionPolicy(
                str(policy).upper()
                if not isinstance(policy, SourcePromotionPolicy)
                else policy
            )
        except ValueError as exc:
            raise InvalidPolicy(str(policy)) from exc

    def promote(self, source, policy, snapshot_root=None):
        if not isinstance(policy, SourcePromotionPolicy):
            raise InvalidPolicy(str(policy))
        recorded = promotion_policy_of(source)
        if (
            recorded is SourcePromotionPolicy.LOCAL_ONLY
            or policy is SourcePromotionPolicy.LOCAL_ONLY
        ):
            raise PromotionDenied("LOCAL_ONLY source cannot be promoted")
        if policy is not recorded:
            raise PromotionDenied("promotion must match the declared policy")
        if snapshot_root is not None:
            root = snapshot_root / source.id
            root.mkdir(parents=True, exist_ok=True)
            if policy is SourcePromotionPolicy.SNAPSHOT:
                try:
                    (root / "source").write_bytes(Path(source.uri).read_bytes())
                except OSError as exc:
                    raise UnknownSource(str(exc)) from exc
            (root / "reference.json").write_bytes(to_canonical_json(source))
        return source

    @staticmethod
    def _family_for(path):
        name = path.name.lower()
        if "openspec" in path.parts and name.endswith(".md"):
            return "openspec"
        if name.endswith((".md", ".markdown")):
            return "markdown"
        if name.endswith((".html", ".htm")):
            return "html"
        if name.endswith(".java"):
            return "java_source"
        if name.endswith(".jar"):
            return "jar"
        if name == "pom.xml" or name.endswith(".pom"):
            return "maven_pom"
        if name.endswith((".gradle", ".gradle.kts")):
            return "gradle_build"
        if name.endswith(".pdf"):
            return "pdf"
        if "openapi" in name:
            return "openapi"
        return "plain_text"


def promotion_policy_of(source):
    return SourcePromotionPolicy(source.metadata.policy or "LOCAL_ONLY")

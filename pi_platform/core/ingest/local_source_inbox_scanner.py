"""LocalSourceInboxScanner core implementation.

Honours the documented ``LOCAL_ONLY`` / ``REFERENCE`` / ``SNAPSHOT``
promotion policy from architecture §9.2. The scanner records the
policy in :attr:`Source.metadata` so downstream stages can branch
on the policy without re-reading ``project-context.yaml``.

The override resolution rule (longest matching glob wins; ties
broken by sort ascending by glob string) is implemented in
:meth:`LocalSourceInboxScanner.resolve_policy` and is locked by
``.ai/wiki/adr/0007-phase-2-inbox-policy-default.md``.
"""

from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.canonical.value_types import (
    KnowledgeState,
    Metadata,
    Source,
)

from pi_platform.ports.ingest.local_source_inbox_scanner import (
    InvalidPolicy,
    LocalSourceInboxContext,
    LocalSourceInboxReport,
    LocalSourceInboxScannerPort,
    PromotionDenied,
    SourcePromotionPolicy,
    UnknownSource,
)


__all__ = ["LocalSourceInboxScanner"]


class LocalSourceInboxScanner(LocalSourceInboxScannerPort):
    """Default :class:`LocalSourceInboxScannerPort` implementation."""

    #: File suffixes registered by default.
    KNOWN_SUFFIXES = {
        ".md", ".markdown",
        ".html", ".htm",
        ".txt", ".text",
        ".java",
        ".jar",
        ".pom",
        ".gradle", ".kts",
        ".yaml", ".yml",
        ".json",
        ".pdf",
        ".openapi.yaml", ".openapi.yml", ".openapi.json",
    }

    def scan(self, context: LocalSourceInboxContext) -> LocalSourceInboxReport:
        if not context.project_root.exists():
            return LocalSourceInboxReport(
                scanned_paths=(),
                registered_sources=(),
                knowledge_state=KnowledgeState.UNKNOWN,
                rationale=f"project_root {context.project_root!r} does not exist",
            )

        sources: list[Source] = []
        scanned: list[Path] = []
        skipped: list[Path] = []
        promoted: list[Path] = []

        iterator: Sequence[Path]
        if context.recursive:
            iterator = tuple(sorted(p for p in context.project_root.rglob("*")))
        else:
            iterator = tuple(sorted(p for p in context.project_root.iterdir()))

        for path in iterator:
            if not path.is_file():
                continue
            if not self._is_known(path):
                skipped.append(path)
                continue
            scanned.append(path)
            policy = self.resolve_policy(
                path, context.default_policy, context.override_map
            )
            source = self._make_source(path, context, policy)
            if policy == SourcePromotionPolicy.SNAPSHOT:
                promoted.append(path)
            sources.append(source)

        return LocalSourceInboxReport(
            scanned_paths=tuple(scanned),
            registered_sources=tuple(sources),
            skipped_paths=tuple(skipped),
            promoted_paths=tuple(promoted),
            knowledge_state=KnowledgeState.VERIFIED,
        )

    def resolve_policy(self, source_path: Path,
                       default_policy: SourcePromotionPolicy,
                       override_map: Mapping[str, SourcePromotionPolicy]
                       ) -> SourcePromotionPolicy:
        candidates = [
            (glob, policy) for glob, policy in override_map.items()
            if fnmatch.fnmatch(str(source_path), glob)
        ]
        if not candidates:
            return default_policy
        candidates.sort(key=lambda gp: (-len(gp[0]), gp[0]))
        return candidates[0][1]

    def promote(self, source: Source, policy: SourcePromotionPolicy,
                snapshot_root: Optional[Path] = None) -> Source:
        if not isinstance(policy, SourcePromotionPolicy):
            raise InvalidPolicy(f"policy must be SourcePromotionPolicy, got {policy!r}")
        if policy == SourcePromotionPolicy.LOCAL_ONLY:
            raise PromotionDenied(
                "LOCAL_ONLY sources cannot be promoted to durable storage"
            )
        # REFERENCE keeps the same bytes on disk; SNAPSHOT copies the
        # source into ``snapshot_root`` if provided. The Phase 2
        # implementation is the canonical guard; the Phase 3
        # RuntimeStore owns the durable materialisation.
        if policy == SourcePromotionPolicy.SNAPSHOT and snapshot_root is not None:
            snapshot_root.mkdir(parents=True, exist_ok=True)
            target = snapshot_root / source.id
            try:
                target.write_bytes(Path(source.uri).read_bytes())
            except FileNotFoundError as exc:
                raise UnknownSource(f"source uri {source.uri!r} not found") from exc
        return source

    def _is_known(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        if suffix in self.KNOWN_SUFFIXES:
            return True
        return any(str(path).endswith(s) for s in self.KNOWN_SUFFIXES)

    def _make_source(self, path: Path, context: LocalSourceInboxContext,
                     policy: SourcePromotionPolicy) -> Source:
        try:
            data = path.read_bytes()
        except OSError:
            data = b""
        content_hash = hashlib.sha256(data).hexdigest()
        metadata = Metadata(
            documentId=content_hash[:12],
            version="0.0.0",
            language="und",
            sourcePath=str(path),
            contentHash=content_hash,
        )
        # The policy is recorded in source.metadata via a side-channel
        # field. We use a fresh Metadata instance so the canonical
        # serializer stays deterministic and the policy survives the
        # round trip.
        object.__setattr__(metadata, "_promotionPolicy", policy.value)
        return Source(
            id=content_address(metadata),
            uri=str(path),
            family=self._family_for(path),
            contentHash=content_hash,
            metadata=metadata,
        )

    @staticmethod
    def _family_for(path: Path) -> str:
        name = path.name.lower()
        if name.endswith((".md", ".markdown")):
            return "markdown"
        if name.endswith((".html", ".htm")):
            return "html"
        if name.endswith((".java",)):
            return "java_source"
        if name.endswith(".jar"):
            return "jar"
        if name.endswith(".pom") or name == "pom.xml":
            return "maven_pom"
        if name.endswith((".gradle", ".kts")):
            return "gradle_build"
        if "openapi" in name and name.endswith((".yaml", ".yml", ".json")):
            return "openapi"
        if name.endswith(".pdf"):
            return "pdf"
        return "plain_text"


def promotion_policy_of(source: Source) -> SourcePromotionPolicy:
    """Return the policy recorded in :attr:`Source.metadata`."""

    raw = object.__getattribute__(source.metadata, "_promotionPolicy")
    return SourcePromotionPolicy(raw)

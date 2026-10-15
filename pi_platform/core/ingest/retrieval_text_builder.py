"""Deterministic retrieval-text builders (Change Package B4).

The default builder assembles ``retrieval_text`` from an allowlist of
semantic fields only, so absolute paths, SHAs, Git commits,
timestamps, bbox coordinates, security labels and processing versions
can never leak into the embedding input. The opt-in
:class:`LocalContextualizerRetrievalTextBuilder` appends a local
contextualizer summary as an explicitly ``inferred:`` part; inferred
text may never overwrite or impersonate authoritative metadata.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional

from pi_platform.core.canonical.value_types import Chunk, Document, Metadata, Section
from pi_platform.ports.ingest.retrieval_text_builder import (
    DEFAULT_STRATEGY_VERSION,
    RetrievalText,
    RetrievalTextBuilderError,
    RetrievalTextBuilderPort,
)


__all__ = [
    "DeterministicRetrievalTextBuilder",
    "LocalContextualizerRetrievalTextBuilder",
]


# Keys whose values must never appear in the deterministic prefix.
_FORBIDDEN_KEYS = frozenset(
    {
        "sourcepath",
        "absolutepath",
        "contenthash",
        "gitcommit",
        "gitrevision",
        "timestamp",
        "bbox",
        "securityclassification",
        "securityclass",
        "processingversion",
        "parserversion",
        "license",
        "sha",
    }
)

# Authoritative keys the local contextualizer is forbidden to produce.
_AUTHORITATIVE_KEYS = frozenset(
    {
        "requirementid",
        "requirement_id",
        "protocolversion",
        "protocol_version",
        "validfrom",
        "validto",
        "securityclass",
        "security_class",
        "gitrevision",
        "git_revision",
        "sourceid",
        "source_id",
        "license",
    }
)

_NEVER_EMBED_KEYS = _FORBIDDEN_KEYS | _AUTHORITATIVE_KEYS

_SHA_VALUE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_ABSOLUTE_PATH = re.compile(
    r"(?:^|[\s\"'(\[])(?:"
    r"/(?:home|Users|root|tmp|var|etc|opt|mnt|srv|workspace|usr|proc|dev|media)/\S*"
    r"|[A-Za-z]:[\\/]\S*"
    r")"
)
_TIMESTAMP_VALUE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?\b")
_FORBIDDEN_LINE_KEY = re.compile(
    r"(?:^|[\s])("
    + "|".join(sorted(_NEVER_EMBED_KEYS, key=len, reverse=True))
    + r")\s*:",
    re.IGNORECASE,
)


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_")


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _value_is_forbidden(value: str) -> bool:
    """Return whether ``value`` looks like a never-embed field."""

    stripped = value.strip()
    if _SHA_VALUE.match(stripped):
        return True
    if _ABSOLUTE_PATH.search(stripped):
        return True
    if _TIMESTAMP_VALUE.search(stripped):
        return True
    return False


def _forbidden_values(
    metadata: Optional[Metadata], document: Optional[Document]
) -> list[tuple[str, str]]:
    """Collect never-embed values actually carried by the inputs."""

    collected: list[tuple[str, str]] = []
    for owner in (metadata, getattr(document, "metadata", None)):
        if owner is None:
            continue
        for attribute in (
            "sourcePath",
            "contentHash",
            "gitCommit",
            "securityClassification",
        ):
            value = getattr(owner, attribute, None)
            if value:
                collected.append((attribute, str(value)))
        extensions = owner.extensions or {}
        for key in (
            "bbox",
            "timestamp",
            "ingestedAt",
            "processedAt",
            "parserVersion",
            "processingVersion",
            "gitRevision",
            "sourceHash",
        ):
            value = extensions.get(key)
            if value:
                collected.append((key, str(value)))
    return [(key, value) for key, value in collected if len(value) >= 8]


class DeterministicRetrievalTextBuilder(RetrievalTextBuilderPort):
    """Default builder: semantic allowlist only, no model required."""

    strategy_version = DEFAULT_STRATEGY_VERSION

    def build(
        self,
        *,
        chunk: Chunk,
        document: Optional[Document],
        section: Optional[Section],
        metadata: Optional[Metadata],
        local_enrichment: Optional[object] = None,
    ) -> RetrievalText:
        """Build ``retrieval_text`` ignoring any local enrichment."""

        del local_enrichment  # the deterministic builder never consumes it
        effective = metadata if metadata is not None else chunk.metadata
        parts = self._deterministic_parts(
            chunk=chunk, document=document, section=section, metadata=effective
        )
        prefix = "\n".join(parts)
        self._verify_prefix(prefix, metadata=effective, document=document)
        text = self._assemble(parts, chunk.rawText)
        return RetrievalText(
            text=text,
            strategy_version=self.strategy_version,
            deterministic_parts=parts,
            inferred_parts=(),
            content_hash=_sha256_hex(text),
        )

    def _deterministic_parts(
        self,
        *,
        chunk: Chunk,
        document: Optional[Document],
        section: Optional[Section],
        metadata: Metadata,
    ) -> tuple[str, ...]:
        extensions = metadata.extensions or {}
        candidates = (
            ("document_title", getattr(document, "title", None)),
            (
                "section",
                getattr(section, "heading", None) or metadata.section,
            ),
            ("businessDomain", metadata.businessDomain),
            ("module", metadata.module),
            ("className", metadata.className),
            ("requirementId", metadata.requirementId),
            ("caption", extensions.get("caption")),
            (
                "protocol_name",
                extensions.get("protocol_name") or extensions.get("protocolName"),
            ),
        )
        parts = []
        for key, value in candidates:
            if not value:
                continue
            text_value = str(value)
            if _value_is_forbidden(text_value):
                raise RetrievalTextBuilderError(
                    f"semantic field {key!r} carries a forbidden value"
                )
            parts.append(f"{key}: {text_value}")
        del chunk  # raw text is appended by _assemble, not as a prefix part
        return tuple(parts)

    def _verify_prefix(
        self, prefix: str, *, metadata: Metadata, document: Optional[Document]
    ) -> None:
        """Raise when a never-embed value or key reaches the prefix."""

        if not prefix:
            return
        for key, value in _forbidden_values(metadata, document):
            if value and value in prefix:
                raise RetrievalTextBuilderError(
                    f"forbidden field {key!r} leaked into the retrieval text prefix"
                )
        for line in prefix.splitlines():
            raw_key, separator, _ = line.partition(":")
            if separator and _normalize_key(raw_key) in _FORBIDDEN_KEYS:
                raise RetrievalTextBuilderError(
                    f"forbidden key {raw_key.strip()!r} in the retrieval text prefix"
                )

    @staticmethod
    def _assemble(parts: tuple[str, ...], raw_text: str) -> str:
        prefix = "\n".join(parts)
        if not prefix:
            return raw_text
        return f"{prefix}\n\n{raw_text}"


def _sanitize_inferred(summary: str) -> str:
    """Drop never-embed keyed lines and collapse whitespace."""

    kept = []
    for line in str(summary).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _FORBIDDEN_LINE_KEY.search(stripped):
            continue
        kept.append(stripped)
    return " ".join(kept)


class LocalContextualizerRetrievalTextBuilder(DeterministicRetrievalTextBuilder):
    """Opt-in builder appending a local contextualizer summary.

    The summary is read from ``local_enrichment.context_summary`` (or
    ``.summary`` for :class:`LocalContextSummary`-shaped objects) and
    recorded under an explicit ``inferred:`` prefix; never-embed keyed
    lines are discarded so a proposed authoritative identifier can
    never enter the embedding input.
    """

    def build(
        self,
        *,
        chunk: Chunk,
        document: Optional[Document],
        section: Optional[Section],
        metadata: Optional[Metadata],
        local_enrichment: Optional[object] = None,
    ) -> RetrievalText:
        base = super().build(
            chunk=chunk,
            document=document,
            section=section,
            metadata=metadata,
        )
        summary = self._summary_of(local_enrichment)
        if not summary:
            return base
        sanitized = _sanitize_inferred(summary)
        if not sanitized:
            return base
        inferred = (f"inferred: {sanitized}",)
        parts = base.deterministic_parts + inferred
        text = self._assemble(parts, chunk.rawText)
        return RetrievalText(
            text=text,
            strategy_version=self.strategy_version,
            deterministic_parts=base.deterministic_parts,
            inferred_parts=inferred,
            content_hash=_sha256_hex(text),
        )

    @staticmethod
    def _summary_of(local_enrichment: Optional[object]) -> str:
        if local_enrichment is None:
            return ""
        value = getattr(local_enrichment, "context_summary", None)
        if value is None:
            value = getattr(local_enrichment, "summary", None)
        return str(value or "")

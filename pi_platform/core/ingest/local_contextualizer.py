"""LocalContextualizer application service (Change Package B5).

A narrow, opt-in service over :class:`LocalLLMPort` (ADR-0027) that
produces only inferred retrieval hints: a 1–3 sentence context
summary, candidate entities, candidate relations and query aliases /
glossary hints. Authoritative metadata (``requirement_id``,
``protocol_version``, ``validFrom`` / ``validTo``, ``security_class``,
``git_revision``, ``source_id``, ``license``) is forbidden: keyed
lines carrying those names are filtered out of every completion, and
the service never writes to canonical metadata itself.

When the active :class:`InferencePolicy` is ``NO_MODEL`` the service
returns an empty summary without invoking the LLM at all. Results are
memoised in a small LRU keyed by
``sha256(chunk.contentHash|model_version|family|prompt_version|enrichment_strategy_version|neighbour_text)``
so a Git branch switch with identical content reuses the summary.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from pi_platform.core.canonical.value_types import Chunk, Document, Section
from pi_platform.ports.ingest.inference_policy import (
    DEFAULT_INFERENCE_POLICY,
    InferencePolicy,
    policy_allows,
)
from pi_platform.ports.orchestration.local_llm import LocalLLMPort


__all__ = [
    "LocalContextSummary",
    "LocalContextualizer",
    "PROMPT_VERSION",
]


PROMPT_VERSION = "v1"
"""Fixed prompt revision; changing it invalidates the context cache."""

_DEFAULT_MAX_SUMMARY_CHARS = 480
_DEFAULT_CACHE_SIZE = 128
_DEFAULT_MAX_TOKENS = 96

# Normalised (lowercase, separator-free) keys the LLM may never set.
_FORBIDDEN_KEYS = frozenset(
    {
        "requirementid",
        "protocolversion",
        "validfrom",
        "validto",
        "securityclass",
        "gitrevision",
        "sourceid",
        "license",
    }
)

_SUMMARY_KEYS = frozenset({"summary", "context", "contextsummary", "description"})
_ENTITY_KEYS = frozenset({"entities", "entity", "candidateentities"})
_RELATION_KEYS = frozenset({"relations", "relation", "candidaterelations"})
_ALIAS_KEYS = frozenset({"aliases", "alias", "queryaliases", "glossary"})

_PROMPT_TEMPLATE = """\
You are a retrieval context assistant for a software project.
Summarise the chunk in at most three short sentences for search.
Then optionally emit hint lines exactly in these forms:
entities: comma, separated, names
relations: comma, separated, triples
aliases: comma, separated, query, rewrites
Rules: never invent identifiers, versions, dates, security labels,
revisions, source ids or licences. Never mention requirement IDs,
protocol versions, validity dates, security classes, Git revisions,
source IDs or licences.
Document title: {title}
Section: {section}
Neighbour text: {neighbour}
Chunk:
{chunk}
"""


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("_", "").replace(" ", "")


def _split_values(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LocalContextSummary:
    """Inferred contextualisation output; never authoritative metadata."""

    summary: str
    candidate_entities: tuple[str, ...] = ()
    candidate_relations: tuple[str, ...] = ()
    query_aliases: tuple[str, ...] = ()
    model_revision: str = ""
    prompt_version: str = PROMPT_VERSION
    content_hash: str = ""


class LocalContextualizer:
    """Policy-gated, cached local-LLM contextualisation service."""

    def __init__(
        self,
        llm: LocalLLMPort,
        *,
        policy: InferencePolicy = DEFAULT_INFERENCE_POLICY,
        max_summary_chars: int = _DEFAULT_MAX_SUMMARY_CHARS,
        prompt_version: str = PROMPT_VERSION,
        cache_size: int = _DEFAULT_CACHE_SIZE,
        enrichment_strategy_version: str = "v1",
    ) -> None:
        if llm is None:
            raise ValueError("llm binding is required")
        if max_summary_chars <= 0:
            raise ValueError(f"max_summary_chars must be > 0, got {max_summary_chars}")
        if cache_size <= 0:
            raise ValueError(f"cache_size must be > 0, got {cache_size}")
        self._llm = llm
        self._policy = policy
        self._max_summary_chars = max_summary_chars
        self._prompt_version = prompt_version
        self._enrichment_strategy_version = enrichment_strategy_version
        self._cache: OrderedDict[str, LocalContextSummary] = OrderedDict()
        self._cache_size = cache_size

    @property
    def policy(self) -> InferencePolicy:
        return self._policy

    def summarize(
        self,
        *,
        chunk: Chunk,
        document: Optional[Document],
        section: Optional[Section],
        neighbour_text: str = "",
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> LocalContextSummary:
        """Return an inferred summary; empty when the policy blocks models."""

        if not policy_allows(self._policy, model_kind="local"):
            return self._summary("", (), (), (), model_revision="")
        prompt = self._prompt(
            chunk=chunk,
            document=document,
            section=section,
            neighbour_text=neighbour_text,
        )
        raw = self._llm.complete(prompt, max_tokens=max_tokens, temperature=0.0)
        summary, entities, relations, aliases = self._parse(raw or "")
        return self._summary(summary, entities, relations, aliases)

    def cache_key(self, *, chunk: Chunk, neighbour_text: str = "") -> str:
        """Return the contextualisation cache key for ``chunk``.

        The key is
        ``sha256(chunk.contentHash|model_version|family|prompt_version|enrichment_strategy_version|neighbour_text)``
        per the context-enrichment delta; changing any component
        invalidates the memoised summary.
        """

        payload = "|".join(
            (
                str(chunk.contentHash or ""),
                str(self._llm.model_version()),
                str(self._llm.family()),
                self._prompt_version,
                self._enrichment_strategy_version,
                neighbour_text,
            )
        )
        return _sha256_hex(payload)

    def cached_summarize(
        self,
        chunk: Chunk,
        neighbour_text: str = "",
        *,
        document: Optional[Document] = None,
        section: Optional[Section] = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> tuple[LocalContextSummary, bool]:
        """Memoised :meth:`summarize`; the flag reports a cache hit."""

        key = self.cache_key(chunk=chunk, neighbour_text=neighbour_text)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached, True
        summary = self.summarize(
            chunk=chunk,
            document=document,
            section=section,
            neighbour_text=neighbour_text,
            max_tokens=max_tokens,
        )
        self._cache[key] = summary
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return summary, False

    def _summary(
        self,
        summary: str,
        entities: tuple[str, ...],
        relations: tuple[str, ...],
        aliases: tuple[str, ...],
        *,
        model_revision: Optional[str] = None,
    ) -> LocalContextSummary:
        content_hash = _sha256_hex(
            "|".join(
                (
                    summary,
                    ",".join(entities),
                    ",".join(relations),
                    ",".join(aliases),
                )
            )
        )
        return LocalContextSummary(
            summary=summary,
            candidate_entities=entities,
            candidate_relations=relations,
            query_aliases=aliases,
            model_revision=(
                str(self._llm.model_version())
                if model_revision is None
                else model_revision
            ),
            prompt_version=self._prompt_version,
            content_hash=content_hash,
        )

    def _prompt(
        self,
        *,
        chunk: Chunk,
        document: Optional[Document],
        section: Optional[Section],
        neighbour_text: str,
    ) -> str:
        """Render the fixed prompt from semantic inputs only.

        Authoritative metadata fields are deliberately never passed to
        the model: the prompt carries the raw text, the document
        title, the section name and the neighbour text — nothing else.
        """

        title = getattr(document, "title", "") or ""
        section_name = getattr(section, "heading", None) or chunk.metadata.section or ""
        return _PROMPT_TEMPLATE.format(
            title=title,
            section=section_name,
            neighbour=neighbour_text or "",
            chunk=chunk.rawText,
        )

    def _parse(
        self, raw: str
    ) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        """Parse ``key: value`` lines, dropping forbidden keys."""

        summary_parts: list[str] = []
        entities: list[str] = []
        relations: list[str] = []
        aliases: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            key, separator, value = stripped.partition(":")
            if not separator:
                summary_parts.append(stripped)
                continue
            normalised = _normalize_key(key)
            if normalised in _FORBIDDEN_KEYS:
                continue
            value = value.strip()
            if normalised in _SUMMARY_KEYS:
                if value:
                    summary_parts.append(value)
            elif normalised in _ENTITY_KEYS:
                entities.extend(_split_values(value))
            elif normalised in _RELATION_KEYS:
                relations.extend(_split_values(value))
            elif normalised in _ALIAS_KEYS:
                aliases.extend(_split_values(value))
            # Unknown keys are ignored: only documented shapes survive.
        summary = " ".join(" ".join(summary_parts).split())
        if len(summary) > self._max_summary_chars:
            summary = summary[: self._max_summary_chars]
        return (
            summary,
            tuple(entities),
            tuple(relations),
            tuple(aliases),
        )

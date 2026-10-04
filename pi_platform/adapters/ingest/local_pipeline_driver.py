"""Default ``PipelineDriverPort`` implementation.

Implements the §18 ingestion pipeline coordinator: the ordered
five-stage sequence parse -> chunk -> enrich -> emit -> store, the
per-stage error-handling contract (transient no-op in Phase 2,
permanent aborts the source, configuration_error aborts the
pipeline, cancelled flushes and stops), per-chunk SHA-256 content
addressing through the runtime cache, and the ``PipelineReport``
instrumentation returned to the caller.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Sequence

from pi_platform.adapters.fs.local_source_adapter import LocalSourceAdapter
from pi_platform.adapters.html.html_adapter import HtmlAdapter
from pi_platform.adapters.ingest.chunkers import (
    HtmlChunker,
    MarkdownChunker,
    PlainTextChunker,
)
from pi_platform.adapters.ingest.layered_context_enricher import (
    LayeredContextEnricher,
)
from pi_platform.adapters.java.gradle_adapter import GradleAdapter
from pi_platform.adapters.java.jar_adapter import JarAdapter
from pi_platform.adapters.java.java_structured_adapter import (
    JavaStructuredAdapter,
    JavaStructuredChunker,
)
from pi_platform.adapters.java.maven_adapter import MavenAdapter
from pi_platform.adapters.markdown.markdown_adapter import MarkdownAdapter
from pi_platform.adapters.openspec.openspec_change_adapter import (
    OpenSpecChangeAdapter,
    OpenSpecChunker,
)

from pi_platform.core.canonical.content_address import content_address_bytes
from pi_platform.core.canonical.value_types import (
    ContextualChunk,
    KnowledgeState,
    Source,
    to_canonical_json,
)
from pi_platform.core.ingest.runtime_cache import InMemoryRuntimeCache

from pi_platform.ports.ingest.chunker import ChunkerError, ChunkerRegistry
from pi_platform.ports.ingest.context_enricher import (
    ContextEnricherPort,
)
from pi_platform.ports.ingest.pipeline_driver import (
    CancellationToken,
    PipelineDriverPort,
    PipelineReport,
    StageError,
    StageErrorCategory,
    StageOutcome,
)
from pi_platform.ports.ingest.source_adapter import (
    AdapterMissing,
    SourceAdapterError,
    SourceAdapterRegistry,
    SourceContentFamily,
)


__all__ = [
    "LocalPipelineDriver",
    "ContextEnricherRegistry",
]


STAGE_PARSE = "parse"
STAGE_CHUNK = "chunk"
STAGE_ENRICH = "enrich"
STAGE_EMIT = "emit"
STAGE_STORE = "store"

STAGE_SEQUENCE = (
    STAGE_PARSE,
    STAGE_CHUNK,
    STAGE_ENRICH,
    STAGE_EMIT,
    STAGE_STORE,
)


class ContextEnricherRegistry:
    """Simple dict wrapper mapping content families to enrichers."""

    DEFAULT_FAMILIES: Sequence[SourceContentFamily] = (
        SourceContentFamily.MARKDOWN,
        SourceContentFamily.HTML,
        SourceContentFamily.PLAIN_TEXT,
        SourceContentFamily.JAVA_SOURCE,
        SourceContentFamily.JAR,
        SourceContentFamily.MAVEN_POM,
        SourceContentFamily.GRADLE_BUILD,
        SourceContentFamily.OPENSPEC,
    )

    def __init__(self,
                 enrichers: Optional[Sequence[ContextEnricherPort]] = None
                 ) -> None:
        self._enrichers: dict[SourceContentFamily, ContextEnricherPort] = {}
        if enrichers is None:
            enrichers = [
                LayeredContextEnricher(family=family)
                for family in self.DEFAULT_FAMILIES
            ]
        for enricher in enrichers:
            self.register(enricher)

    def register(self, enricher: ContextEnricherPort) -> None:
        self._enrichers[enricher.family] = enricher

    def resolve(self, family: SourceContentFamily) -> ContextEnricherPort:
        enricher = self._enrichers.get(family)
        if enricher is not None:
            return enricher
        fallback = self._enrichers.get(SourceContentFamily.PLAIN_TEXT)
        if fallback is not None:
            return fallback
        return LayeredContextEnricher()


def _default_parser_registry() -> SourceAdapterRegistry:
    registry = SourceAdapterRegistry()
    for adapter in (
        MarkdownAdapter(),
        HtmlAdapter(),
        LocalSourceAdapter(),
        JavaStructuredAdapter(),
        JarAdapter(),
        MavenAdapter(),
        GradleAdapter(),
        OpenSpecChangeAdapter(),
    ):
        registry.register(adapter)
    return registry


def _default_chunker_registry() -> ChunkerRegistry:
    registry = ChunkerRegistry()
    for chunker in (
        MarkdownChunker(),
        HtmlChunker(),
        PlainTextChunker(),
        JavaStructuredChunker(),
        OpenSpecChunker(),
    ):
        registry.register(chunker)
    return registry


class LocalPipelineDriver(PipelineDriverPort):
    """Default §18 ingestion pipeline coordinator."""

    def __init__(self, *,
                 parser_registry: Optional[SourceAdapterRegistry] = None,
                 chunker_registry: Optional[ChunkerRegistry] = None,
                 enricher_registry: Optional[ContextEnricherRegistry] = None,
                 cache=None) -> None:
        self._parsers = (
            parser_registry if parser_registry is not None
            else _default_parser_registry()
        )
        self._chunkers = (
            chunker_registry if chunker_registry is not None
            else _default_chunker_registry()
        )
        self._enrichers = (
            enricher_registry if enricher_registry is not None
            else ContextEnricherRegistry()
        )
        self._cache = cache if cache is not None else InMemoryRuntimeCache()

    def run(self, source: Source, project_root: Path, *,
            cancellation: Optional[CancellationToken] = None,
            cache=None) -> PipelineReport:
        active_cache = cache if cache is not None else self._cache
        stages: List[StageOutcome] = []
        hits = 0
        misses = 0
        chunk_count = 0
        stage = STAGE_PARSE

        def outcome(name: str, *, count: int = 0, hit: bool = False,
                    started: Optional[float] = None,
                    error_category: Optional[str] = None,
                    error_message: Optional[str] = None) -> StageOutcome:
            duration_ms = (
                0.0 if started is None
                else (time.perf_counter() - started) * 1000.0
            )
            return StageOutcome(
                stage=name,
                cache_hit=hit,
                output_count=count,
                duration_ms=duration_ms,
                error_category=error_category,
                error_message=error_message,
            )

        def report_with_error(name: str, category: str,
                              message: str) -> PipelineReport:
            stages.append(outcome(name, error_category=category,
                                  error_message=message))
            return PipelineReport(
                source_id=source.id,
                content_hash=source.contentHash,
                stages=tuple(stages),
                chunk_count=chunk_count,
                cache_hit_count=hits,
                cache_miss_count=misses,
                knowledge_state=KnowledgeState.UNKNOWN,
                error_category=category,
                error_message=message,
            )

        def cancelled() -> bool:
            return cancellation is not None and cancellation.is_cancelled()

        try:
            family = SourceContentFamily(source.family)
        except ValueError as exc:
            return report_with_error(
                stage, StageErrorCategory.CONFIGURATION.value, str(exc),
            )

        if cancelled():
            return report_with_error(
                stage, StageErrorCategory.CANCELLED.value,
                "pipeline cancelled before parse",
            )

        try:
            started = time.perf_counter()
            adapter = self._parsers.resolve(family)
            parsed = adapter.parse(source)
            stages.append(outcome(stage, count=len(parsed.sections),
                                  started=started))

            stage = STAGE_CHUNK
            if cancelled():
                return report_with_error(
                    stage, StageErrorCategory.CANCELLED.value,
                    "pipeline cancelled before chunk",
                )
            started = time.perf_counter()
            chunker = self._chunkers.resolve(adapter.family)
            chunks = chunker.chunk(parsed.document, parsed.sections)
            chunk_count = len(chunks)
            stages.append(outcome(stage, count=chunk_count, started=started))

            stage = STAGE_ENRICH
            if cancelled():
                return report_with_error(
                    stage, StageErrorCategory.CANCELLED.value,
                    "pipeline cancelled before enrich",
                )
            started = time.perf_counter()
            enricher = self._enrichers.resolve(adapter.family)
            enriched: List[ContextualChunk] = []
            for chunk in chunks:
                content_hash = content_address_bytes(to_canonical_json(chunk))
                if active_cache.get(content_hash) is not None:
                    hits += 1
                    continue
                misses += 1
                contextual, _reports = enricher.enrich((chunk,))
                enriched.extend(contextual)
                active_cache.put(content_hash, to_canonical_json(chunk))
            stages.append(outcome(stage, count=len(enriched),
                                  hit=hits > 0, started=started))

            stage = STAGE_EMIT
            if cancelled():
                return report_with_error(
                    stage, StageErrorCategory.CANCELLED.value,
                    "pipeline cancelled before emit",
                )
            started = time.perf_counter()
            stages.append(outcome(stage, count=len(enriched), started=started))

            stage = STAGE_STORE
            if cancelled():
                return report_with_error(
                    stage, StageErrorCategory.CANCELLED.value,
                    "pipeline cancelled before store",
                )
            started = time.perf_counter()
            stages.append(outcome(stage, count=len(enriched), started=started))
        except StageError as exc:
            return report_with_error(stage, exc.category.value, str(exc))
        except (AdapterMissing, ChunkerError) as exc:
            return report_with_error(
                stage, StageErrorCategory.CONFIGURATION.value, str(exc),
            )
        except SourceAdapterError as exc:
            return report_with_error(
                stage, StageErrorCategory.PERMANENT.value, str(exc),
            )
        except Exception as exc:
            return report_with_error(
                stage, StageErrorCategory.PERMANENT.value, str(exc),
            )

        return PipelineReport(
            source_id=source.id,
            content_hash=source.contentHash,
            stages=tuple(stages),
            chunk_count=chunk_count,
            cache_hit_count=hits,
            cache_miss_count=misses,
            knowledge_state=KnowledgeState.VERIFIED,
        )

    def run_many(self, sources: Sequence[Source], project_root: Path, *,
                 cancellation: Optional[CancellationToken] = None,
                 cache=None) -> Sequence[PipelineReport]:
        reports: List[PipelineReport] = []
        for source in sources:
            report = self.run(source, project_root,
                              cancellation=cancellation, cache=cache)
            reports.append(report)
            if report.error_category in (
                StageErrorCategory.CONFIGURATION.value,
                StageErrorCategory.CANCELLED.value,
            ):
                break
        return tuple(reports)

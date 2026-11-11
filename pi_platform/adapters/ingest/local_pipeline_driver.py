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

from pi_platform.adapters.python.intelligence import PythonManifestAdapter, PythonSourceAdapter, PythonWheelAdapter
from pi_platform.adapters.research.lock_ingest import (
    NodeLockAdapter,
    NodeManifestAdapter,
    PythonLockAdapter,
)

import time
from pathlib import Path
from typing import List, Optional, Sequence

from pi_platform.adapters.fs.local_source_adapter import LocalSourceAdapter
from pi_platform.adapters.html.html_adapter import HtmlAdapter
from pi_platform.adapters.office.office_adapter import OfficeAdapter
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

    def __init__(
        self, enrichers: Optional[Sequence[ContextEnricherPort]] = None
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
        OfficeAdapter(),
        LocalSourceAdapter(),
        JavaStructuredAdapter(),
        JarAdapter(),
        PythonManifestAdapter(),
        PythonSourceAdapter(),
        PythonWheelAdapter(),
        NodeManifestAdapter(),
        NodeLockAdapter(),
        PythonLockAdapter(),
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
        *[
            DependencyChunker(f)
            for f in (
                SourceContentFamily.OFFICE,
                SourceContentFamily.JAR,
                SourceContentFamily.PYTHON_SOURCE,
                SourceContentFamily.PYTHON_MANIFEST,
                SourceContentFamily.PYTHON_WHEEL,
                SourceContentFamily.MAVEN_POM,
                SourceContentFamily.GRADLE_BUILD,
                SourceContentFamily.PYTHON_LOCK,
                SourceContentFamily.NODE_MANIFEST,
                SourceContentFamily.NODE_LOCK,
            )
        ],
    ):
        registry.register(chunker)
    return registry


class DependencyChunker(PlainTextChunker):
    def __init__(self, family):
        self.family = family


class LocalPipelineDriver(PipelineDriverPort):
    """Five stages with cached completion, bounded retry and runtime record emission."""

    def __init__(
        self,
        *,
        parser_registry=None,
        chunker_registry=None,
        enricher_registry=None,
        cache=None,
        project_version=None,
        chunker_context=None,
        enricher_context=None,
        retry_delay=0.01,
        parse_workers=None,
        resource_pool=None,
        parallel_safe_registry=False,
        memory_probe=None,
        worker_peak_estimator=None,
        memory_target_percent=50,
    ):
        self._parsers = (
            parser_registry
            if parser_registry is not None
            else _default_parser_registry()
        )
        self._chunkers = (
            chunker_registry
            if chunker_registry is not None
            else _default_chunker_registry()
        )
        self._enrichers = (
            enricher_registry
            if enricher_registry is not None
            else ContextEnricherRegistry()
        )
        self._cache = cache if cache is not None else InMemoryRuntimeCache()
        self.project_version = project_version
        self.chunker_context = chunker_context
        self.enricher_context = enricher_context
        self.retry_delay = retry_delay
        from pi_platform.adapters.runtime.host_resources import parse_worker_budget
        from pi_platform.core.orchestration.resource_budget import ResourceTokenPool
        self.parse_workers = parse_worker_budget(parse_workers)
        self.resource_pool = resource_pool or ResourceTokenPool(self.parse_workers)
        self._parallel_safe = (
            parser_registry is None and chunker_registry is None and enricher_registry is None
        ) or parallel_safe_registry
        # Optional model adapters may carry session state; they require their own
        # worker factory before sharing an enricher context across sources.
        if self.enricher_context is not None and (
            getattr(self.enricher_context, "enable_optional_llm", False)
            or getattr(self.enricher_context, "local_contextualizer", None) is not None
            or (getattr(self.enricher_context, "extra", {}) or {}).get("local_llm") is not None
        ):
            self._parallel_safe = False
        if not 0 < memory_target_percent <= 100:
            raise ValueError("memory target must be in (0, 100]")
        from pi_platform.adapters.runtime.host_resources import probe_available_memory, estimate_source_worker_peak
        self.memory_probe = memory_probe or probe_available_memory
        self.worker_peak_estimator = worker_peak_estimator or estimate_source_worker_peak
        self.memory_target_percent = memory_target_percent
        self.last_admission = {}

    def _resolve_chunker(self, family, chunk_ctx):
        """Return the structural chunker, token-budget-wrapped when needed.

        Change Package B3 wiring: when the active ``ChunkerContext``
        carries token fields (``target_tokens`` / ``max_tokens``) the
        structural chunker is wrapped with a
        :class:`TokenBudgetNormalizer` so oversized pieces are split and
        compatible peers merged. With no token fields set the legacy
        byte-based chunker is returned untouched.
        """
        structural = self._chunkers.resolve(family)
        has_token_fields = (
            getattr(chunk_ctx, "target_tokens", None) is not None
            or getattr(chunk_ctx, "max_tokens", None) is not None
        )
        if not has_token_fields:
            return structural
        try:
            from pi_platform.adapters.ingest.tokenizers import HashingTokenizer
            from pi_platform.core.ingest.token_budget import TokenBudgetNormalizer

            max_chunk_bytes = (
                chunk_ctx.max_chunk_bytes
                if getattr(chunk_ctx, "max_chunk_bytes", 0) > 0
                else 16384
            )
            normalizer = TokenBudgetNormalizer(
                HashingTokenizer(),
                max_chunk_bytes=max_chunk_bytes,
            )
            return normalizer.wrap(structural)
        except Exception:
            return structural

    def _apply_retrieval_text(self, contextual_chunks, enrich_ctx):
        """Build ``retrieval_text`` for each enriched chunk (B4 wiring).

        Uses :class:`DeterministicRetrievalTextBuilder` by default. When
        a :class:`LocalContextualizer` is wired on the enricher context
        and its inference policy allows local models, the opt-in
        :class:`LocalContextualizerRetrievalTextBuilder` is used so the
        contextualizer summary is appended as an explicit ``inferred:``
        part. The built text and its content hash are stored under
        ``chunk.metadata.extensions``; ``contextualText`` mirrors the
        retrieval text when one was produced.
        """
        import dataclasses

        from pi_platform.core.ingest.retrieval_text_builder import (
            DeterministicRetrievalTextBuilder,
            LocalContextualizerRetrievalTextBuilder,
        )

        local_contextualizer = getattr(enrich_ctx, "local_contextualizer", None)
        use_local = False
        if local_contextualizer is not None:
            try:
                from pi_platform.ports.ingest.inference_policy import (
                    policy_allows,
                )

                use_local = policy_allows(
                    local_contextualizer.policy, model_kind="local",
                )
            except Exception:
                use_local = False
        builder = (
            LocalContextualizerRetrievalTextBuilder()
            if use_local
            else DeterministicRetrievalTextBuilder()
        )
        document = getattr(enrich_ctx, "document", None) or None
        output = []
        for contextual in contextual_chunks:
            chunk = contextual.chunk
            local_enrichment = None
            if use_local:
                assumption = (chunk.metadata.extensions or {}).get(
                    "pi_assumption",
                ) or {}
                summary_text = assumption.get("context_summary") or ""
                if summary_text:
                    from types import SimpleNamespace

                    local_enrichment = SimpleNamespace(
                        context_summary=summary_text,
                    )
            try:
                retrieval = builder.build(
                    chunk=chunk,
                    document=document,
                    section=None,
                    metadata=chunk.metadata,
                    local_enrichment=local_enrichment,
                )
            except Exception:
                output.append(contextual)
                continue
            extensions = dict(chunk.metadata.extensions or {})
            extensions["retrieval_text"] = retrieval.text
            extensions["retrieval_text_hash"] = retrieval.content_hash
            new_chunk = dataclasses.replace(
                chunk,
                metadata=dataclasses.replace(chunk.metadata, extensions=extensions),
            )
            if retrieval.text:
                new_chunk = dataclasses.replace(
                    new_chunk, contextualText=retrieval.text,
                )
            output.append(dataclasses.replace(contextual, chunk=new_chunk))
        return tuple(output)

    def pipeline_key(self, source):
        """Return the source/configuration compatibility key without cache access."""
        from pi_platform.core.canonical.content_address import content_address
        from pi_platform.core.canonical.value_types import dataclass_to_dict
        return content_address(
            {
                "source": source.contentHash,
                "uri": source.uri,
                "metadata": dataclass_to_dict(source.metadata),
                "pipelineVersion": "phase2-2",
                "chunking": (
                    dataclass_to_dict(self.chunker_context)
                    if self.chunker_context
                    else None
                ),
                "enrichment": (
                    dataclass_to_dict(self.enricher_context)
                    if self.enricher_context
                    else None
                ),
                "parsers": [
                    (
                        f.value,
                        type(self._parsers.resolve(f)).__name__,
                        getattr(
                            getattr(self._parsers.resolve(f), "parser", None),
                            "parser_version",
                            None,
                        ),
                    )
                    for f in self._parsers.families()
                ],
            }
        )

    def run(self, source, project_root, *, cancellation=None, cache=None):
        import json
        import logging
        import dataclasses
        from datetime import datetime, timezone
        from pi_platform.core.canonical.content_address import (
            content_address,
            chunk_content_address,
        )
        from pi_platform.ports.ingest.source_adapter import SourceAdapterContext
        from pi_platform.ports.ingest.java_parser import (
            JavaParserMissing,
            JavaParserVersionMismatch,
            JavaParserTimeout,
            JavaParserCorruptOutput,
        )

        log = logging.getLogger(__name__)
        active = cache if cache is not None else self._cache
        if hasattr(active, "source_buffer"):
            active = active.source_buffer(source.id)
        started_at = datetime.now(timezone.utc).isoformat()
        stages, chunks, enriched, addresses = [], (), (), []
        parsed = None
        hits = misses = 0
        stage = STAGE_PARSE
        state = {
            "LOCAL_ONLY": KnowledgeState.UNKNOWN,
            "REFERENCE": KnowledgeState.ASSUMPTION,
        }.get(source.metadata.policy, KnowledgeState.VERIFIED)
        key = self.pipeline_key(source)

        def report(category=None, message=None):
            return PipelineReport(
                source.id,
                source.contentHash,
                tuple(stages),
                len(chunks),
                len(parsed.entities) if parsed else 0,
                len(parsed.relations) if parsed else 0,
                len(parsed.evidence) if parsed else 0,
                hits,
                misses,
                state if category is None else KnowledgeState.UNKNOWN,
                category,
                message,
                self.project_version,
                (source,),
                started_at,
                datetime.now(timezone.utc).isoformat(),
                degraded=bool(parsed and parsed.knowledge_state is not KnowledgeState.VERIFIED),
            )

        def flush():
            for chunk in chunks:
                raw = to_canonical_json(chunk)
                k = content_address_bytes(raw) if getattr(active, "immutable_payloads", False) else chunk_content_address(chunk)
                active.put(k, raw)
                addresses.append(k)

        def checkpoint_cancel():
            if cancellation is not None and cancellation.is_cancelled():
                flush()
                raise StageError(
                    StageErrorCategory.CANCELLED,
                    "pipeline cancelled; partial chunks flushed",
                )

        def operation(name, function):
            nonlocal stage
            stage = name
            checkpoint_cancel()
            started = time.perf_counter()
            for attempt in range(1, 5):
                try:
                    result = function()
                    stages.append(
                        StageOutcome(
                            name,
                            False,
                            len(result) if isinstance(result, (tuple, list)) else 1,
                            (time.perf_counter() - started) * 1000,
                            source_id=source.id,
                            attempts=attempt,
                        )
                    )
                    log.info(
                        "stage=%s source=%s attempt=%s outcome=ok",
                        name,
                        source.id,
                        attempt,
                    )
                    return result
                except (JavaParserTimeout, StageError) as exc:
                    category = (
                        StageErrorCategory.TRANSIENT
                        if isinstance(exc, JavaParserTimeout)
                        else exc.category
                    )
                    log.warning(
                        "stage=%s source=%s attempt=%s category=%s",
                        name,
                        source.id,
                        attempt,
                        category.value,
                    )
                    if category is not StageErrorCategory.TRANSIENT or attempt == 4:
                        raise StageError(category, str(exc)) from exc
                    checkpoint_cancel()
                    time.sleep(min(self.retry_delay * 2 ** (attempt - 1), 1.0))

        try:
            for registered_family in self._parsers.families():
                registered_parser = getattr(
                    self._parsers.resolve(registered_family), "parser", None
                )
                if (
                    registered_parser is not None
                    and getattr(registered_parser, "required", False)
                    and not registered_parser.is_available()
                ):
                    raise JavaParserMissing(
                        "required Java parser unavailable; no sources processed"
                    )
            family = SourceContentFamily(source.family)
            self._parsers.resolve(family)
            self._chunkers.resolve(family)
            checkpoint_cancel()
            previous = (
                active.source_record(source.id)
                if hasattr(active, "source_record")
                else None
            )
            if previous and (
                previous["hash"] != source.contentHash or previous["key"] != key
            ):
                active.invalidate_source(source.id, stale=False)
            cached = active.get(key)
            if cached is not None:
                data = json.loads(cached)
                hits = data["chunkCount"]
                state = KnowledgeState(data["knowledgeState"])
                stages = [
                    StageOutcome(
                        name,
                        True,
                        data.get("chunkCount", 0),
                        0,
                        source_id=source.id,
                        outcome="skipped",
                        content_addresses=tuple(data["addresses"]),
                    )
                    for name in STAGE_SEQUENCE
                ]
                return dataclasses.replace(
                    report(),
                    chunk_count=data["chunkCount"],
                    entity_count=data["entityCount"],
                    relation_count=data["relationCount"],
                    evidence_count=data["evidenceCount"],
                    degraded=bool(data.get("degraded", False)),
                )
            adapter = self._parsers.resolve(family)
            parsed = operation(
                STAGE_PARSE,
                lambda: adapter.parse(
                    source,
                    SourceAdapterContext(
                        Path(project_root),
                        project_version=self.project_version,
                        cancellation=cancellation,
                    ),
                ),
            )
            if parsed.knowledge_state is not KnowledgeState.VERIFIED:
                state = parsed.knowledge_state
            from pi_platform.ports.ingest.chunker import ChunkerContext
            from pi_platform.ports.ingest.context_enricher import EnricherContext

            chunk_ctx = dataclasses.replace(
                self.chunker_context or ChunkerContext(),
                source_hash=source.contentHash,
                cancellation=cancellation,
            )
            enrich_ctx = dataclasses.replace(
                self.enricher_context or EnricherContext(),
                document=parsed.document,
                source=source,
                project_version=self.project_version,
                cancellation=cancellation,
            )
            active_chunker = self._resolve_chunker(family, chunk_ctx)
            chunks = operation(
                STAGE_CHUNK,
                lambda: active_chunker.chunk(
                    parsed.document, parsed.sections, chunk_ctx
                ),
            )
            if state is not KnowledgeState.VERIFIED:
                chunks = tuple(
                    dataclasses.replace(
                        c,
                        provenance=dataclasses.replace(
                            c.provenance, knowledgeState=state, rationale=source.uri
                        ),
                    )
                    for c in chunks
                )

            def enrich():
                nonlocal hits, misses
                output = []
                for c in chunks:
                    checkpoint_cancel()
                    body_key = chunk_content_address(c)
                    if active.get(body_key) is not None:
                        hits += 1
                    else:
                        misses += 1
                    # Body reuse never suppresses source-derived metadata/provenance updates.
                    contextual, _ = self._enrichers.resolve(family).enrich(
                        (c,), enrich_ctx
                    )
                    output.extend(self._apply_retrieval_text(contextual, enrich_ctx))
                return tuple(output)

            enriched = operation(STAGE_ENRICH, enrich)
            records = operation(
                STAGE_EMIT,
                lambda: (*parsed.entities, *parsed.relations, *parsed.evidence),
            )

            def store():
                for c in chunks:
                    raw = to_canonical_json(c)
                    k = content_address_bytes(raw) if getattr(active, "immutable_payloads", False) else chunk_content_address(c)
                    active.put(k, raw)
                    addresses.append(k)
                for record in (*enriched, *records):
                    raw = to_canonical_json(record)
                    k = content_address_bytes(raw)
                    active.put(k, raw)
                    addresses.append(k)
                return tuple(addresses)

            operation(STAGE_STORE, store)
            for i, outcome in enumerate(stages):
                stages[i] = dataclasses.replace(
                    outcome, content_addresses=tuple(addresses)
                )
            data = {
                "chunkCount": len(chunks),
                "entityCount": len(parsed.entities),
                "relationCount": len(parsed.relations),
                "evidenceCount": len(parsed.evidence),
                "knowledgeState": state.value,
                "degraded": parsed.knowledge_state is not KnowledgeState.VERIFIED,
                "addresses": addresses,
            }
            checkpoint_cancel()
            active.put(key, json.dumps(data, sort_keys=True).encode())
            if hasattr(active, "complete_source"):
                active.complete_source(
                    source.id,
                    source.contentHash,
                    key,
                    addresses,
                    content_address(to_canonical_json(source.metadata).decode()),
                )
            return report()
        except (
            ValueError,
            AdapterMissing,
            ChunkerError,
            JavaParserMissing,
            JavaParserVersionMismatch,
        ) as exc:
            category = StageErrorCategory.CONFIGURATION
            message = str(exc)
        except StageError as exc:
            category = exc.category
            message = str(exc)
        except (SourceAdapterError, JavaParserCorruptOutput) as exc:
            category = StageErrorCategory.PERMANENT
            message = str(exc)
        except Exception as exc:
            # Anything reaching this handler is outside the failure
            # vocabulary the pipeline documents for the operator (source
            # errors, configuration errors, retries). Treat it as an
            # internal programming bug rather than a permanent source
            # error so the operator can distinguish "the source is bad"
            # from "the code has a regression" without having to dig
            # through tracebacks. ``logger.exception`` ensures the
            # traceback lands in the diagnostic stream alongside the
            # ``INTERNAL`` category marker.
            category = StageErrorCategory.INTERNAL
            message = f"unexpected internal error: {exc!r}"
            log.exception(
                "stage=%s source=%s category=internal_error exc_type=%s",
                stage,
                source.id,
                type(exc).__name__,
            )
        stages.append(
            StageOutcome(
                stage,
                False,
                0,
                0,
                error_category=category.value,
                error_message=message,
                source_id=source.id,
                outcome="failed",
            )
        )
        log.warning(
            "stage=%s source=%s category=%s error=%s",
            stage,
            source.id,
            category.value,
            message,
        )
        return report(category.value, message)

    def run_many(self, sources, project_root, *, cancellation=None, cache=None):
        from concurrent.futures import ThreadPoolExecutor
        import logging
        log = logging.getLogger(__name__)
        active = cache if cache is not None else self._cache
        reports = []
        workers = self.parse_workers if self._parallel_safe and hasattr(active, "source_buffer") else 1
        diagnostics = self.last_admission = {
            "cpu_worker_limit": workers, "peak_pending_workers": 0,
            "peak_reserved_bytes": 0, "minimum_memory_budget_bytes": None,
            "serialized_sources": 0, "unknown_estimates": 0,
            "memory_limited_sources": 0,
        }

        def execute(source):
            cost = self.resource_pool.capacity if source.family == "pdf" else 1
            with self.resource_pool.acquire(cost):
                return self.run(source, project_root, cancellation=cancellation, cache=active)

        if workers == 1:
            for source in sources:
                result = execute(source)
                reports.append(result)
                if result.error_category in ("configuration_error", "cancelled"):
                    break
            return tuple(reports)

        pending = []
        reserved = 0

        def collect_first():
            nonlocal reserved
            future, estimate = pending.pop(0)
            result = future.result()
            reserved -= estimate
            reports.append(result)
            return result.error_category not in ("configuration_error", "cancelled")

        try:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for source in sources:
                    if cancellation is not None and cancellation.is_cancelled():
                        break
                    available = self.memory_probe()
                    budget = None if available is None else max(0, int(available * self.memory_target_percent / 100))
                    estimate = self.worker_peak_estimator(source)
                    if estimate is not None and estimate <= 0:
                        estimate = None
                    if budget is not None:
                        previous = diagnostics["minimum_memory_budget_bytes"]
                        diagnostics["minimum_memory_budget_bytes"] = budget if previous is None else min(previous, budget)
                    # Unknown/oversized documents get exclusive admission. This bounds
                    # parallel allocations; it does not claim a hard per-source RSS cap.
                    serial = source.family in ("pdf", "office") or estimate is None or budget is None or estimate > budget
                    if serial:
                        diagnostics["serialized_sources"] += 1
                        if estimate is None or budget is None:
                            diagnostics["unknown_estimates"] += 1
                        elif estimate > budget:
                            diagnostics["memory_limited_sources"] += 1
                        log.info("source admission=serial source=%s estimate_bytes=%s memory_budget_bytes=%s",
                                 source.id, estimate, budget)
                        while pending:
                            if not collect_first():
                                return tuple(reports)
                        result = execute(source)
                        reports.append(result)
                        if result.error_category in ("configuration_error", "cancelled"):
                            break
                        continue
                    limited = False
                    while pending and (len(pending) >= workers or reserved + estimate > budget):
                        limited = limited or reserved + estimate > budget
                        if not collect_first():
                            return tuple(reports)
                    if limited:
                        diagnostics["memory_limited_sources"] += 1
                    pending.append((executor.submit(execute, source), estimate))
                    reserved += estimate
                    diagnostics["peak_pending_workers"] = max(diagnostics["peak_pending_workers"], len(pending))
                    diagnostics["peak_reserved_bytes"] = max(diagnostics["peak_reserved_bytes"], reserved)
                while pending:
                    if not collect_first():
                        break
                return tuple(reports)
        finally:
            for future, _ in pending:
                future.cancel()
            log.info("source admission summary=%s", diagnostics)

"""Three-layer ContextEnricher implementation.

Covers architecture sections §22 (three-layer context enrichment),
§54 (metadata-only fields) and §55 (freshness and provenance).
The enricher produces :class:`ContextualChunk` records whose
``contextPrefix`` is the deterministic concatenation of the
applied-layer outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from pi_platform.core.canonical.value_types import (
    Chunk,
    ContextualChunk,
    KnowledgeState,
    Metadata,
)

from pi_platform.ports.ingest.context_enricher import (
    ContextEnricherPort,
    ContextEnricherReport,
    DomainRule,
    EnricherContext,
    EnricherError,
    EnrichmentLayer,
)
from pi_platform.ports.ingest.source_adapter import SourceContentFamily


__all__ = ["LayeredContextEnricher"]


@dataclass(frozen=True)
class _LayeredResult:
    chunk_id: str
    chunk: Chunk
    metadata: Metadata
    prefix: str
    applied: Tuple[EnrichmentLayer, ...]
    knowledge_state: KnowledgeState


class LayeredContextEnricher(ContextEnricherPort):
    """Default three-layer enricher.

    Layer 1 (DETERMINISTIC) populates the metadata fields that can
    be derived from the chunk's source bytes. It NEVER invents
    authoritative identifiers, versions, dates or security
    classifications (§22.3 contract).

    Layer 2 (DOMAIN_RULE) augments the metadata with deterministic
    domain rules sourced from ``project-context.yaml:ingest.
    domainRules``.

    Layer 3 (OPTIONAL_LLM) is disabled by default; when enabled it
    emits an ``pi_assumption`` block. The Phase 2 implementation
    stubs the layer with a deterministic no-op so the contract is
    exercised; the Phase 5 ``LocalLLMPort`` provides the binding.
    """

    def __init__(self, family: SourceContentFamily = SourceContentFamily.PLAIN_TEXT) -> None:
        self._family = family

    @property
    def family(self) -> SourceContentFamily:
        return self._family

    def enrich(self, chunks: Sequence[Chunk],
               context: Optional[EnricherContext] = None
               ) -> Tuple[Sequence[ContextualChunk], Sequence[ContextEnricherReport]]:
        if context is None:
            context = EnricherContext()
        contextual: List[ContextualChunk] = []
        reports: List[ContextEnricherReport] = []
        for chunk in chunks:
            result = self._enrich_one(chunk, context)
            contextual.append(
                ContextualChunk(chunk=result.chunk,
                                contextPrefix=result.prefix)
            )
            reports.append(
                ContextEnricherReport(
                    chunk_id=result.chunk_id,
                    applied_layers=result.applied,
                    duration_ms=0.0,
                    knowledge_state=result.knowledge_state,
                )
            )
        return tuple(contextual), tuple(reports)

    def _enrich_one(self, chunk: Chunk, context: EnricherContext) -> _LayeredResult:
        applied: List[EnrichmentLayer] = [EnrichmentLayer.DETERMINISTIC]
        metadata = self._deterministic_layer(chunk, context)
        prefix = self._format_prefix(EnrichmentLayer.DETERMINISTIC, metadata)

        rule_metadata, matched_rule = self._domain_rule_layer(chunk, context)
        if matched_rule:
            applied.append(EnrichmentLayer.DOMAIN_RULE)
            metadata = self._merge_metadata(metadata, rule_metadata)
            prefix += "\n" + self._format_prefix(EnrichmentLayer.DOMAIN_RULE, metadata)

        knowledge_state = context.knowledge_state_default
        if context.enable_optional_llm:
            applied.append(EnrichmentLayer.OPTIONAL_LLM)
            llm_metadata, llm_prefix = self._optional_llm_layer(chunk, context)
            metadata = self._merge_metadata(metadata, llm_metadata)
            prefix += "\n" + llm_prefix
            knowledge_state = KnowledgeState.ASSUMPTION

        result_chunk = self._chunk_with(chunk, metadata)
        return _LayeredResult(
            chunk_id=result_chunk.id,
            chunk=result_chunk,
            metadata=metadata,
            prefix=prefix,
            applied=tuple(applied),
            knowledge_state=knowledge_state,
        )

    def _deterministic_layer(self, chunk: Chunk,
                             context: EnricherContext) -> Metadata:
        base = chunk.metadata
        # Populate the deterministic metadata fields from the chunk.
        # Layer 1 NEVER invents authoritative identifiers; it only
        # reflects the source bytes. If a field is missing in the
        # chunk, it is left as None.
        return Metadata(
            documentId=base.documentId,
            version=base.version,
            language=base.language,
            section=base.section,
            businessDomain=base.businessDomain,
            module=base.module,
            className=base.className,
            requirementId=base.requirementId,
            validFrom=base.validFrom,
            validTo=base.validTo,
            gitCommit=base.gitCommit,
            sourcePath=base.sourcePath,
            page=base.page,
            line=base.line,
            securityClassification=base.securityClassification,
            contentHash=base.contentHash,
        )

    def _domain_rule_layer(self, chunk: Chunk,
                           context: EnricherContext) -> Tuple[Metadata, Optional[DomainRule]]:
        for rule in context.domain_rules:
            if rule.path_glob and chunk.metadata.sourcePath:
                if not _glob_match(chunk.metadata.sourcePath, rule.path_glob):
                    continue
            if rule.content_family is not None and rule.content_family != self._family:
                continue
            metadata = Metadata(
                documentId=chunk.metadata.documentId,
                version=chunk.metadata.version,
                language=chunk.metadata.language,
                section=chunk.metadata.section,
                businessDomain=rule.metadata.get("businessDomain"),
                module=rule.metadata.get("module") or chunk.metadata.module,
                className=rule.metadata.get("className") or chunk.metadata.className,
                requirementId=chunk.metadata.requirementId,
                validFrom=chunk.metadata.validFrom,
                validTo=chunk.metadata.validTo,
                gitCommit=chunk.metadata.gitCommit,
                sourcePath=chunk.metadata.sourcePath,
                page=chunk.metadata.page,
                line=chunk.metadata.line,
                securityClassification=rule.metadata.get(
                    "securityClassification"
                ) or chunk.metadata.securityClassification,
                contentHash=chunk.metadata.contentHash,
            )
            return metadata, rule
        return chunk.metadata, None

    def _optional_llm_layer(self, chunk: Chunk,
                            context: EnricherContext) -> Tuple[Metadata, str]:
        # Phase 5 will provide the binding. The Phase 2 stub emits a
        # deterministic ``pi_assumption`` block listing the candidate
        # context fields the LLM might enrich; the actual values are
        # never written to authoritative metadata fields.
        prefix = "## pi_assumption\ncandidate_entities: []\ncandidate_relations: []\n"
        return chunk.metadata, prefix

    @staticmethod
    def _format_prefix(layer: EnrichmentLayer, metadata: Metadata) -> str:
        if layer is EnrichmentLayer.DETERMINISTIC:
            return (
                f"## {layer.value}\n"
                f"documentId: {metadata.documentId}\n"
                f"version: {metadata.version}\n"
                f"language: {metadata.language}\n"
                f"sourcePath: {metadata.sourcePath or ''}\n"
                f"contentHash: {metadata.contentHash or ''}\n"
            )
        if layer is EnrichmentLayer.DOMAIN_RULE:
            return (
                f"## {layer.value}\n"
                f"businessDomain: {metadata.businessDomain or ''}\n"
                f"module: {metadata.module or ''}\n"
                f"className: {metadata.className or ''}\n"
                f"securityClassification: {metadata.securityClassification or ''}\n"
            )
        return f"## {layer.value}\n(stub)\n"

    @staticmethod
    def _merge_metadata(*metadatas: Metadata) -> Metadata:
        result: dict = {}
        for metadata in metadatas:
            for field in (
                "documentId", "version", "language", "section",
                "businessDomain", "module", "className",
                "requirementId", "validFrom", "validTo",
                "gitCommit", "sourcePath", "page", "line",
                "securityClassification", "contentHash",
            ):
                value = getattr(metadata, field, None)
                if value is not None and field not in result:
                    result[field] = value
        return Metadata(
            documentId=result.get("documentId", ""),
            version=result.get("version", "0.0.0"),
            language=result.get("language", "und"),
            section=result.get("section"),
            businessDomain=result.get("businessDomain"),
            module=result.get("module"),
            className=result.get("className"),
            requirementId=result.get("requirementId"),
            validFrom=result.get("validFrom"),
            validTo=result.get("validTo"),
            gitCommit=result.get("gitCommit"),
            sourcePath=result.get("sourcePath"),
            page=result.get("page"),
            line=result.get("line"),
            securityClassification=result.get("securityClassification"),
            contentHash=result.get("contentHash"),
        )

    @staticmethod
    def _chunk_with(chunk: Chunk, metadata: Metadata) -> Chunk:
        import dataclasses
        return dataclasses.replace(chunk, metadata=metadata)


def _glob_match(path: str, glob: str) -> bool:
    import fnmatch
    return fnmatch.fnmatch(path, glob)

"""Source-derived metadata and explicit assumption provenance for enrichment."""

import fnmatch
import logging
from dataclasses import replace
from pi_platform.core.canonical.content_address import chunk_content_address
from pi_platform.core.canonical.value_types import ContextualChunk, KnowledgeState
from pi_platform.ports.ingest.context_enricher import (
    ContextEnricherPort,
    ContextEnricherReport,
    EnricherContext,
    EnricherError,
    EnrichmentLayer,
)
from pi_platform.ports.ingest.source_adapter import SourceContentFamily

log = logging.getLogger(__name__)


class LayeredContextEnricher(ContextEnricherPort):
    def __init__(self, family=SourceContentFamily.PLAIN_TEXT):
        self._family = family

    @property
    def family(self):
        return self._family

    def enrich(self, chunks, context=None):
        context = context or EnricherContext()
        result, reports = [], []
        for chunk in chunks:
            layers = [EnrichmentLayer.DETERMINISTIC]
            source = context.source
            document = context.document
            version = context.project_version
            meta = replace(
                chunk.metadata,
                contentHash=chunk_content_address(chunk),
                documentId=document.id if document else chunk.metadata.documentId,
                sourcePath=source.uri if source else chunk.metadata.sourcePath,
                version=source.metadata.version if source else chunk.metadata.version,
                gitCommit=version.gitHead if version else chunk.metadata.gitCommit,
                line=chunk.metadata.line or chunk.metadata.extensions.get("line"),
            )
            state = chunk.provenance.knowledgeState
            for rule in context.domain_rules:
                if not meta.sourcePath or not fnmatch.fnmatch(
                    meta.sourcePath, rule.path_glob
                ):
                    continue
                if rule.content_family and rule.content_family != self.family:
                    continue
                changes = {
                    k: v
                    for k, v in rule.metadata.items()
                    if k
                    in (
                        "businessDomain",
                        "module",
                        "className",
                        "securityClassification",
                    )
                }
                extras = dict(meta.extensions)
                for k in ("system", "candidateEntities"):
                    if k in rule.metadata:
                        extras[k] = rule.metadata[k]
                extras["pi_rule_state"] = "assumption"
                meta = replace(meta, **changes, extensions=extras)
                state = KnowledgeState.ASSUMPTION
                layers.append(EnrichmentLayer.DOMAIN_RULE)
                log.info(
                    "domain rule chunk=%s glob=%s state=assumption",
                    chunk.id,
                    rule.path_glob,
                )
            if context.enable_optional_llm:
                binding = context.extra.get("local_llm")
                if binding is None:
                    raise EnricherError("enabled LLM layer requires a local binding")
                if meta.policy not in (
                    "LOCAL_ONLY",
                    "REFERENCE",
                ) or not context.extra.get("allow_local_llm"):
                    raise EnricherError(
                        "source policy does not explicitly permit local LLM input"
                    )
                suggestion = binding(
                    chunk.rawText, max_tokens=int(context.extra.get("max_tokens", 256))
                )
                allowed = {
                    k: v
                    for k, v in suggestion.items()
                    if k in ("contextPrefix", "entities", "relations")
                }
                meta = replace(
                    meta,
                    extensions={
                        **meta.extensions,
                        "pi_assumption": {**allowed, "knowledgeState": "assumption"},
                    },
                )
                state = KnowledgeState.ASSUMPTION
                layers.append(EnrichmentLayer.OPTIONAL_LLM)
            prefix = "\n".join(
                f"{k}: {v}"
                for k, v in (
                    ("section", meta.section),
                    ("sourcePath", meta.sourcePath),
                    ("requirementId", meta.requirementId),
                )
                if v
            )
            evidence = replace(chunk.provenance, knowledgeState=state)
            result.append(
                ContextualChunk(
                    replace(chunk, metadata=meta, provenance=evidence), prefix
                )
            )
            reports.append(
                ContextEnricherReport(
                    chunk.id, tuple(layers), 0.0, knowledge_state=state
                )
            )
        return tuple(result), tuple(reports)

---
id: interfaces.enrichment
title: Context enrichment interface
kind: interfaces
status: active
summary: Context enrichment interface contracts and observed Phase 2 behavior.
sourceRefs:
  - pi_platform/adapters/ingest/local_pipeline_driver.py
  - tests/test_platform_phase2.py
maintenance:
  mode: authored
---

# Context enrichment interface

`ContextEnricherPort.enrich(Chunk[], EnricherContext)` returns contextual chunks and
layer reports. Context includes source, document, project version and cancellation.
The deterministic layer derives metadata and a section/source/requirement prefix.
Domain rules apply configured path globs, preserve authoritative fields, and record
candidate entities/system labels in extensions with assumption provenance.

The optional LLM layer is disabled by default and requires an explicit local binding,
a token budget, and source-policy permission. It accepts only suggested context,
entities and relations, stores them under `extensions.pi_assumption`, and never
replaces authoritative identifiers. A configured LLM without a binding fails clearly;
Phase 2 does not pretend to invoke an unavailable Phase 5 provider.

Metadata has additive optional `policy` and `extensions` fields. Empty additions
are omitted from canonical JSON, preserving Phase 1 serialized bytes. Extensions
retain policy decisions, parser attributes and assumption evidence across round trips.

[Ingestion](../modules/ingest.md) · [Canonical interface](canonical.md)

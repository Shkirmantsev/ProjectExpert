---
id: glossary.domain
title: Domain Glossary
kind: glossary
status: draft
summary: Project-specific terms with stable, reviewed meanings.
sourceRefs: []
maintenance:
  mode: authored
---

# Domain Glossary

Add project terminology alphabetically. Prefer one concise definition plus links to deeper Wiki/OpenSpec material.

For platform-specific vocabulary (canonical knowledge, runtime working
knowledge, hydration, materialisation, OKF, capability, hook,
control plane, data plane, ...), see
[`glossary/platform`](platform.md).


## Phase 2 ingestion

The [ingestion module](../modules/ingest.md) implements PipelineDriver, source adapters,
structural chunking, layered enrichment, content-address reuse and inbox policies.
SourcePromotionPolicy distinguishes LOCAL_ONLY, REFERENCE and SNAPSHOT; parser
subprocesses and cache records carry explicit provenance. See the
[source interface](../interfaces/source-adapters.md), [chunker](../interfaces/chunker.md)
and [enrichment](../interfaces/enrichment.md) contracts. Persistent storage and retrieval
remain future phases.

---
id: modules.ingest
title: Phase 2 ingestion
kind: modules
status: active
summary: Phase 2 ingestion contracts and observed Phase 2 behavior.
sourceRefs:
  - pi_platform/adapters/ingest/local_pipeline_driver.py
  - pi_platform/core/ingest/repository_source_discovery.py
  - tests/test_platform_phase2.py
  - openspec/specs/2026-10-18-repository-source-discovery-incremental/spec.md
maintenance:
  mode: authored
---

# Phase 2 ingestion

The ingestion pipeline runs parse, chunk, enrich, emit and store. The default
`LocalPipelineDriver` composes document, Java, JAR, build-file and OpenSpec adapters.
The process-local cache stores actual chunks, contextual chunks, entities, relations
and evidence. A completed source manifest skips parsing and chunking on repeat runs;
source changes invalidate owned cache records, and deletions mark derived records stale.
Transient failures retry three times after the first attempt. Permanent failures skip
the source; configuration errors and cancellation stop the queue. Cancellation flushes
completed chunks. Reports record stage outcomes, attempts, addresses and source counts.

Run `python -m pi_platform.cli ingest-sources --target /path/to/repo`.
The default inbox is `tmp/local/source`; runtime evidence and cache exports are under
`tmp/local/pi-platform-ingest`. Configuration comes from
`project-knowledge/project-context.yaml` or `--config` (JSON also supported).
The command never promotes source bytes into the canonical tree. Promotion remains an
explicit operator operation governed by the declared source policy.

The Java parser is optional; install `.[java]` for structural extraction. Missing
optional parser packages produce metadata-only assumptions. `javaParser.required: true`
makes an unavailable parser a configuration error. JAR public signatures use a stdlib
class-file reader; Maven and Gradle declared graphs do not execute builds during parse.
Explicit `resolve_tree` invokes an available build tool with a 60 second timeout; an
absent tool returns declared edges with a partial-tree advisory. Missing dependency
SPDX identifiers remain assumptions. CLI ingestion records discovered dependencies
locally so the subsequent target license gate cannot silently pass unknown coordinates.

PDF, OpenAPI and office adapters remain planned. Persistent databases, vectors and
sharded graph storage belong to later phases.

## Repository source discovery (production)

`pi_platform.core.ingest.repository_source_discovery.RepositorySourceDiscovery`
walks a target repository, classifies each source into a family
recognised by the ingestion pipeline (source code, canonical
knowledge, OpenSpec change, documentation, configuration) and
produces a content-fingerprinted inventory persisted under
`.project-intelligence-cache/source-inventory.json`. Default
include patterns cover Java, Kotlin, Python, JavaScript,
TypeScript, Gradle, Maven POM, OpenSpec, Markdown, HTML and the
supported API / spec files; default exclude patterns cover
`.git/`, the runtime cache, `target/`, `build/`,
`node_modules/` and the generated vendor directories. A
re-discovery reuses unchanged sources through their content
hash + parser version + retrieval text hash; only ADDED /
MODIFIED / REMOVED sources trigger downstream work. The
inventory is the input the production `start` command consumes
when no previous inventory exists.

See [source adapters](../interfaces/source-adapters.md), [chunking](../interfaces/chunker.md),
[enrichment](../interfaces/enrichment.md), [parser ADR](../adr/0006-phase-2-parser-selection.md)
and [inbox policy ADR](../adr/0007-phase-2-inbox-policy-default.md).

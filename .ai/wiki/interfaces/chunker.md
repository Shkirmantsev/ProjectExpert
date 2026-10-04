---
id: interfaces.chunker
title: Chunker interface
kind: interfaces
status: active
summary: Chunker interface contracts and observed Phase 2 behavior.
sourceRefs:
  - pi_platform/adapters/ingest/local_pipeline_driver.py
  - tests/test_platform_phase2.py
maintenance:
  mode: authored
---

# Chunker interface

`ChunkerPort.chunk(Document, Section[], ChunkerContext)` returns ordered chunks.
Markdown, HTML and plain-text chunks retain actual body text and section parent IDs.
Java class chunks link to the document; method/constructor chunks link to their class,
and non-leaf chunks list child IDs. OpenSpec chunks include complete requirement and
scenario text and link to the specification document.

Default limits are 4096 UTF-8 bytes maximum and 256 bytes minimum. Adjacent small
paragraphs merge within the same section; structural boundaries and terminal fragments
are retained even when below the minimum. Oversized text splits at paragraph/word
boundaries with a code-point-safe fallback. Policy decisions appear in metadata
extensions and operational logs. Repeated identical fragments have position-qualified
stable IDs. Missing structural strategies fail instead of silently using plain text.
Explicit RequirementIdChunker, ProtocolMessageChunker, TableChunker and
ArchitectureUnitChunker strategies support their respective source boundaries; tables
repeat headers in each fragment and preserve fingerprints, architecture units link
nested units. Register these strategies for a target's selected content family.

[Ingestion](../modules/ingest.md) · [Source adapters](source-adapters.md)

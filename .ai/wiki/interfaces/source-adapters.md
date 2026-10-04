---
id: interfaces.source-adapters
title: Source adapter interface
kind: interfaces
status: active
summary: Source adapter interface contracts and observed Phase 2 behavior.
sourceRefs:
  - pi_platform/adapters/ingest/local_pipeline_driver.py
  - tests/test_platform_phase2.py
maintenance:
  mode: authored
---

# Source adapter interface

`SourceAdapterPort.parse(Source, SourceAdapterContext)` returns `SourceParseResult`:
the unchanged source, a document, ordered sections, structured entities, relations,
evidence, parser version and knowledge state. Document IDs equal source IDs. Body
text lives in each section's seed chunks, avoiding an incompatible Section schema.
Missing files, invalid UTF-8, binary NUL prefixes and corrupt archives fail explicitly.
Markdown recognizes headings outside fenced blocks. HTML retains visible body text
and suppresses script/style/head content. The registry rejects unsupported families;
Java-bytecode and OpenSpec family aliases resolve explicitly.

Java structured records include classes/interfaces, methods/constructors, packages,
annotations, inheritance, calls, JPA mappings and JUnit test links. Configuration
properties are an explicit best-effort inferred family. JAR reads public JVM members,
annotations, inherited types, module exports, Maven coordinates and resource paths.
A sibling sources JAR contributes preferred source signatures and source hash evidence.
Coordinates absent from manifest/pom.properties stay unknown rather than invented.

OpenSpec records distinguish active specs, draft changes and archives; archived
records never appear as active OpenSpecChange entities. Shared OKF frontmatter parsing
preserves `pi_` extensions. Requirements link by SATISFIES and PART_OF; referenced
components link by IMPLEMENTED_BY; draft implementation gaps use PENDING assumptions.

[Ingestion module](../modules/ingest.md) · [Chunker](chunker.md)

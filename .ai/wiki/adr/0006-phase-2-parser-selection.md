---
id: adr.phase-2-parser-selection
title: Use an isolated tree-sitter Java parser
kind: adr
status: accepted
summary: Use an isolated tree-sitter Java parser contracts and observed Phase 2 behavior.
sourceRefs:
  - pi_platform/adapters/ingest/local_pipeline_driver.py
  - tests/test_platform_phase2.py
maintenance:
  mode: authored
---

# Use an isolated tree-sitter Java parser

## Decision

Use tree-sitter-java 0.23.5 with tree-sitter Python binding 0.25.2 behind JavaParserPort.
Both pinned releases are MIT licensed and tracked by the dependency inventory.
The preparation draft incorrectly called tree-sitter-java Apache-2.0; upstream
[release LICENSE](https://github.com/tree-sitter/tree-sitter-java/blob/v0.23.5/LICENSE)
is authoritative for the dependency fact. Proposed artifacts were corrected before
adoption; historical Phase 1 specs and archives were retained.

`parser_subprocess.py` owns process creation, version/JSON validation, bounded timeouts
and cleanup. The adapter invokes the Python worker out of process, once per parse;
`subprocess.run` terminates and reaps timed-out children. This deliberately replaces
the draft's persistent-per-project worker with a bounded one-shot lifecycle. The
optional `java` package extra provides native grammar/binding wheels. The core
container keeps Java packages optional and supports metadata-only degraded mode.
Required-parser configuration fails closed. Every constructor checks both inventory
entries and the license gate before adapter activation.

Rejected alternatives: javalang has narrower modern-Java coverage; JavaParser adds a
JVM build/runtime dependency; javap/jdeps cannot preserve source syntax boundaries.
The AST worker exposes structure, not compiler-level name/type resolution. External
inheritance/call targets are source declarations; future semantic resolution remains
behind the port.

[Ingestion](../modules/ingest.md) · [License governance](../interfaces/licensing.md)

---
id: modules.release-gate
title: Production release gate
kind: modules
status: active
summary: The release-time proof that no production component is a stub. The gate runs before declaring a production release; it fails the build on `pinned-stub` / `not bound` / `usearch-stub` / synthetic Docling, on missing real models, and on a non-real dense backend.
sourceRefs:
  - pi_platform/core/orchestration/production_capability_gate.py
  - pi_platform/core/orchestration/production_capability_discovery.py
  - pi_platform/cli/production_capability_gate.py
  - harness.py
  - openspec/changes/production-semantic-search-and-branch-reconciliation/specs/2026-10-18-production-capability-and-release-gates/spec.md
maintenance:
  mode: authored
related:
  - modules.retrieval
  - interfaces.sync
---

# Production release gate

The production-capability gate is the difference between a
working repository and a production-grade release. It is the
last command `harness.py check` runs before declaring a build
green, and the only CLI tool that gives the operator a single
pass / fail answer about whether the running image really
binds every production component.

## What the gate checks

1. **License inventory** — every record in
   `distribution/licenses/model-licenses.json` whose `profile`
   is in the production-enabled set MUST carry a non-stub
   `revision` and `status`. Records that belong to a profile
   listed in `openspec/changes/production-semantic-search-and-branch-reconciliation/excluded-profiles.md`
   are ignored; the gate is deterministic and reviewable.

2. **Docling probe** — the real `docling.document_converter.DocumentConverter`
   must be importable. The probe goes through
   `pi_platform.adapters.pdf.real_docling.is_docling_available()`
   and refuses to accept the synthesised stub path as
   production.

3. **USearch probe** — the real `usearch` native package must be
   importable and the dense index backend must resolve to
   `"usearch"`. The probe goes through
   `is_real_usearch_available()`; a `usearch-stub` backend is
   a hard failure.

4. **Embedding probe** — for every production-enabled profile
   the gate instantiates the embedding model and asks for a
   probe vector. The probe is permitted to SKIP rather than
   FAIL when the cached snapshot is incompatible with the
   installed `sentence-transformers`; a SKIP is informational,
   not a release blocker. An unconditional
   `EmbeddingModelError` from `embed()` is a hard failure.

## API

`pi_platform.core.orchestration.production_capability_gate.run_production_capability_gate()`
returns a `GateReport` with `passed: bool`, `verdicts` (one
per check, each carrying `name`, `passed`, `details`) and
`skipped` (the count of SKIPPED embedding probes).

`pi_platform.cli.production_capability_gate.cmd_production_capability_gate()`
wraps the function with a CLI: pretty-printed JSON output by
default, single-line JSON when called with `--json`, exit 0
when `passed`, exit 1 otherwise.

`harness.py check` runs the CLI as a subprocess step
(`cmd_production_capability_gate()`) between
`cmd_openspec_check()` and `cmd_test()`. The harness refuses
to print "Harness core checks: PASS" if this step fails.

## How to fix when something breaks

- **License inventory stub failure** — the gate message names
  the offending profile + revision. Update
  `distribution/licenses/model-licenses.json` to the real
  pinned SHA, or remove the profile from the production-enabled
  set in the same file.
- **Embedding probe SKIPPED** — the cached EmbeddingGemma 2
  snapshot is incompatible with the installed
  `sentence-transformers`. Re-pull with
  `python -m pi_platform.cli models pull embeddinggemma2` or
  upgrade `sentence-transformers`; this is informational only
  and does NOT fail the release.
- **Docling or USearch import failure** — install the optional
  dependency (`pip install docling docling-core` or
  `pip install usearch`) and re-run.
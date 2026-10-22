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
  - openspec/specs/2026-10-18-production-capability-and-release-gates/spec.md
maintenance:
  mode: authored
related:
  - modules.retrieval
  - interfaces.sync
---

# Production release gate

The default production-capability command verifies real runtime bindings and
model inference. Core harness checks select `--inventory-only`, which validates
pinned model records without requiring optional production dependencies. Core
success is not production release approval. The production license closure has
a separate policy gate; see `docs/PRODUCTION_LICENSE_REVIEW.md`.

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
   finite, normalized probe vector. Missing weights, incompatible loaders,
   unsupported devices and inference errors are hard failures. No failed
   production embedding probe is converted into a skip.

## API

`pi_platform.core.orchestration.production_capability_gate.run_production_capability_gate()`
returns a `GateReport` with `passed: bool`, `verdicts` (one
per check, each carrying `name`, `passed`, `details`) and
`skipped` (zero for the strict production runtime lane).

`pi_platform.cli.production_capability_gate.cmd_production_capability_gate()`
wraps the function with a CLI: pretty-printed JSON output by
default, single-line JSON when called with `--json`, exit 0
when `passed`, exit 1 otherwise.

`harness.py check` runs the CLI as a subprocess step
(`cmd_production_capability_gate()`) between
`cmd_openspec_check()` and `cmd_test()`. The harness uses inventory-only mode and refuses to print
"Harness core checks: PASS" if that inventory check fails. Run the default
production command separately in the installed production environment.

## How to fix when something breaks

- **License inventory stub failure** — the gate message names
  the offending profile + revision. Update
  `distribution/licenses/model-licenses.json` to the real
  pinned SHA, or remove the profile from the production-enabled
  set in the same file.
- **Embedding probe failure** — install the supported production lock and pull
  the exact pinned snapshot with `python -m pi_platform.cli models pull gemma`
  or `qwen`. Retry the strict gate; unsupported cached snapshots remain failures.
- **Docling or USearch import failure** — install the optional
  dependency (`pip install docling docling-core` or
  `pip install usearch`) and re-run.
## Development container and deployment kit

`publish-oci-container.yml` separates core artifacts (`core-*`) from production
(`sha-<full-commit>`, `production`, `dev`, `development`, `main`). The production job checks
an exact hash-bound dependency acceptance, then real default-model startup,
query, UI/MCP and restart through the standalone deployment Compose. It pushes
the tested runtime image and a matching `project-intelligence-deployment` kit
that embeds its digest. PRs do not push. A Windows job tests launcher behavior
with a controlled Docker boundary; it is not a Windows GPU hardware test.

The operator accepted the exact 12-coordinate review on 2026-10-22. Its lock,
inventory and evidence hashes remain mandatory. Real production CPU model setup
and search/restart passed locally; remote publication and physical GPU tests
remain pending.

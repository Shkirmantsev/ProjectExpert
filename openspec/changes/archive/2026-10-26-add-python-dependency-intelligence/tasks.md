## Tasks
- [x] Reproduce and fix migration release, launcher and Wiki regressions.
- [x] Implement static Python manifest, source and wheel adapters with pipeline wiring.
- [x] Verify dependency/API search and failure/partial-analysis cases.
- [x] Run focused tests, broader suite, Wiki/OpenSpec and harness checks.
- [x] Update operator documentation and record hardware/publication limits.

Verification: full suite 1,540 tests (14 optional skips), final focused 17 tests,
real GGUF CPU text/image, final production container search/restart, kit export,
strict OpenSpec validation and final harness check PASS. Hardware/publication
limits are recorded in docs/RUNTIME_PYTHON_REVIEW.md.

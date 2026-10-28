# Baseline and known gaps

Inspected 2026-10-27. These are repository observations, not a reproduction on the user's trade-analyzer installation. Do not access or modify that other repository without a separate task.

| Area | Observed evidence | Consequence |
|---|---|---|
| Default Make | `distribution/deployment/Makefile` sets `.DEFAULT_GOAL := platform-start` and has no help target | Confirmed mismatch with requested help-first behavior; root Makefile already has documented help |
| Orphan warning | `compose.sh` runs `production inference plan` and benchmark helpers with base `compose.yaml`; final startup adds accelerator/backend overlays | Plausible cause: sidecars exist in the project but are absent from helper configuration. Must reproduce with repeated startup before declaring root cause |
| Startup result | User transcript ends with production/embeddings healthy and model-setup exited | Warning alone does not prove startup failed; model setup exit may be normal successful one-shot completion |
| Readiness URL | Kit Makefile interpolates shell `PI_CONTROL_PORT` while Compose reads `deployment.env` | Test env-file-only custom ports and precedence; current message can be misleading |
| Python | `adapters/python/intelligence.py`, `tests/test_python_dependency_intelligence.py`, accepted Python spec and `docs/PYTHON_DEPENDENCY_ANALYSIS.md` | AST, pyproject/requirements and wheel metadata/source exist; constraints and wheel versions do not prove resolved closure |
| Java | `adapters/java/dependencies.py`, `jar_adapter.py`, `classfile.py` | Tree command/parser and source/classfile APIs exist. Classfile signatures are not full method-body decompilation; source/JAR discovery must be verified end to end |
| Node | `core/ingest/repository_source_discovery.py` includes JS/TS and package.json | File discovery does not establish semantic Node resolution or API analysis; node_modules is excluded |
| MCP | `_tool_get_dependency` in `pi_platform/mcp/server.py` echoes three Maven fields with a note | Confirmed research implementation gap despite tool availability |
| A2A | `A2aAdapterCore.invoke` returns an `ack` artifact; `cli/main.py` wires the adapter | Transport/flags exist; successful acknowledgement is not a dependency research result |
| Wiki | `core/wiki/llm_wiki.py`, `project.wiki_*` tools and accepted Wiki spec | Validated atomic writes and navigation exist; dependency freshness, conflict-safe enrichment and read-after-index workflow need explicit coverage |
| README | Historical phases call UI/A2A future; accepted specs and source include them | Correct the temporal mismatch; do not replace it with an unverified claim of full research support |

Paths without a repository prefix above are under `pi_platform/` where applicable. Source evidence is stronger than the historical README phase table. Keep unresolved gaps visible in the implementation handoff.

## Specific discovery checks before selecting optional dependencies

- Inventory lockfile versions supported by the chosen parsers and document exact versions; reject unknown versions explicitly.
- Confirm available offline bytecode readers/decompilers, supported JVM/CPython versions, licensing, resource limits and executable paths in the production image. No particular decompiler has been selected or verified here.
- Verify embedded and standalone route wiring and authentication for Open WebUI and A2A; a default constant is not proof that a service is listening.
- Reproduce Compose warning in a disposable exported kit with the same project name, then trace each helper call. Do not mask stderr or blindly add `--remove-orphans`.

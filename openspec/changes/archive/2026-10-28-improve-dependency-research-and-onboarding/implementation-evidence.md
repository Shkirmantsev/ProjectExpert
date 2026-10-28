# Implementation evidence

Append-only record of what was actually implemented and verified, per
slice. Planning is described in [handoff](handoff.md); this file
records execution. A task in [tasks](tasks.md) may be marked complete
only when its evidence is recorded here.

Environment of the implementation runs:

| Property | Value |
|---|---|
| Host | Linux x86_64, GNU Make 4.3, Docker Compose v5.6.0, Docker Engine available |
| Interpreter | `python3` 3.12 (no `python` alias); the project test runner is `unittest`, not `pytest` |
| Windows host | **NOT RUN** -- no PowerShell and no Windows host are available here |
| Test entry point | `python3 -m unittest tests.<module> -v` (the `harness.py check` runner) |
| Real product image | **NOT RUN** -- the `project-intelligence:production` image was not started with the real model download |

---

## Slice 1 -- deployment help and Compose consistency

### Reproduced root cause of the repeated-start warning

The orphan warning was reproduced with real Docker Compose in a
disposable project that mirrors the kit topology (`production`,
one-shot `model-setup`, `embeddings` sidecar):

| Invocation | Compose file set | Result |
|---|---|---|
| helper | `compose.yaml` only | `Found orphan containers (…-model-setup-1, …-embeddings-1) for this project.` |
| helper | `compose.yaml` + `compose.accelerator.yaml` + `compose.cpu.yaml` | no warning |

The launchers asked the inference plan and the benchmark with the
base `compose.yaml` only, so the healthy sidecar containers of the
deployment were reported as orphans. The warning was a **reduced
configuration**, not a real orphan. `stop.ps1` additionally passed
`--remove-orphans` with the same reduced file set, which could have
deleted the sidecar and model-setup containers.

### Changes

| File | Change |
|---|---|
| `distribution/deployment/Makefile` | `.DEFAULT_GOAL := help`; every public target carries a `##` description; `help` lists them with only Make and `awk`; `platform-start` prints the effective address after readiness |
| `distribution/deployment/url.sh`, `url.ps1` | New: resolve the effective control port (shell environment, then `deployment.env` read as plain text, then `8765`) and print `Ready: <url>` |
| `distribution/deployment/start.sh`, `start.ps1` | Use the shared resolver instead of duplicating the port logic |
| `distribution/deployment/compose.sh` | Helper invocations use the complete applicable topology; the pre-selection plan uses the provisional CPU overlay; `down` also reaches the sidecars of an earlier sidecar deployment |
| `distribution/deployment/compose.ps1`, `setup-windows-accelerator.ps1` | Same complete topology for the measurement, plan and Windows setup helpers |
| `distribution/deployment/stop.ps1` | `--remove-orphans` removed; the complete service topology is stopped instead |
| `distribution/deployment/export.py` | `url.sh` and `url.ps1` are exported |
| `distribution/deployment/README.md`, `docs/PRODUCTION_INSTALL.md` | Document the help-first migration, the effective address and the orphan diagnosis |
| `tests/test_portable_deployment.py` | 16 new tests (help/read-only/port/topology) plus 4 real-Docker Compose acceptance tests |

### Commands and results

```bash
python3 -m unittest tests.test_portable_deployment -v
# Ran 30 tests -- OK
#   includes 4 real-Docker Compose acceptance tests (alpine:latest based)
```

### Unresolved limitations

* **NOT RUN** -- the Windows launcher path (`compose.ps1`, `start.ps1`,
  `stop.ps1`, `setup-windows-accelerator.ps1`) was changed but not
  executed: no Windows host and no PowerShell are available here. The
  PowerShell topology contract is asserted statically by
  `DeploymentTopologyTests.test_the_windows_launcher_uses_the_same_complete_topology`.
* **NOT RUN** -- the real product images were not started: that needs
  the ~310 MB model download and the image pull. The Compose topology
  contract was verified against a disposable project with the same
  service names, health checks and `service_completed_successfully`
  dependency.
* **NOT RUN** -- `scripts/test_deployment_launchers.ps1` (Windows
  launcher contract) for the same reason.
* The **published** GHCR `:dev` kit still carries the pre-change
  Makefile. The help-first behaviour is in this repository and ships
  with the next kit publication; the published image was not rebuilt
  here (publication is out of scope for this change).

---

## Slice 2 -- shared dependency research contract and offline graph

### Changes

| Area | Change |
|---|---|
| `pi_platform/core/research/records.py` | `Package`, `PackageInstance`, `DependencyEdge`, `EvidenceReference`, `SymbolCard`, `EcosystemSnapshot`, `ResearchResult`, the status/completeness/representation enumerations and the typed errors |
| `pi_platform/core/research/policy.py` | `ResearchLimits` and `AcquisitionPolicy`: validated, clamped to the hard maxima, with a fingerprint for cursor binding |
| `pi_platform/core/research/graph.py` | The dependency graph, the stable instance identity and the bounded breadth-first traversal with why-paths |
| `pi_platform/core/research/service.py` | The service: the adapter registry, the snapshot-bound cursors, the truthful status and completeness |
| `pi_platform/ports/research/*.py` | `DependencyResearchPort` (tree/search/read/acquire/capabilities) and `EcosystemResearchPort` |
| `pi_platform/adapters/research/python_locks.py` | `uv.lock` (version 1) and `poetry.lock` (1.1, 2.0, 2.1) readers |
| `pi_platform/adapters/research/python_ecosystem.py` | Declarations, lock resolution, explicitly selected installed metadata, project symbols and the mismatch reports |
| `pi_platform/adapters/research/node_locks.py` | `package.json`, `package-lock.json` (npm 1-3), `pnpm-lock.yaml` (6.0, 9.0) and `yarn.lock` (classic v1, berry v2-v8) readers |
| `pi_platform/adapters/research/node_sources.py` | The tree-sitter JavaScript/TypeScript analysis: exported symbols, imports, re-exports and dynamic imports |
| `pi_platform/adapters/research/node_ecosystem.py` | The Node adapter: workspaces, scopes, aliases, nested versions, the npm resolution rule and the source symbols |
| `pi_platform/adapters/research/java_ecosystem.py` | The Java adapter: the declarations through the existing static adapters and the explicitly selected local repository; never a build tool |
| `pi_platform/adapters/research/lock_ingest.py` | The ingestion adapters that make the lock evidence searchable |
| `pi_platform/ports/ingest/source_adapter.py`, `pi_platform/core/ingest/repository_source_discovery.py`, `pi_platform/core/orchestration/repository_indexing.py`, `pi_platform/adapters/ingest/local_pipeline_driver.py` | The new families `PYTHON_LOCK`, `NODE_MANIFEST` and `NODE_LOCK` wired into the existing discovery and pipeline |

### Decisions

* The Node parser is **tree-sitter** with the MIT-licensed
  `tree-sitter-javascript` and `tree-sitter-typescript` grammars.
  They are an optional extra (`node`), not part of `production`.
* An unknown lock version is rejected with an actionable diagnostic.
  A guessed graph is worse than an explicit "not supported".
* The Java closure is **not** resolved: a dependency-tree command
  executes project code.

### Commands and results

```bash
python3 -m unittest tests.test_dependency_research_service -v
# Ran 53 tests -- OK
```

---

## Slice 3 -- artifact acquisition and library implementation evidence

### Changes

| File | Change |
|---|---|
| `pi_platform/adapters/research/artifacts.py` | The safe, bounded inspection of zip and tar archives: traversal, absolute paths, symlink/hardlink escapes, member count, expanded size, compression ratio and the member read budget |
| `pi_platform/adapters/research/acquisition.py` | The policy-controlled acquisition: the approved source identities, the registry locators, the redirect and host checks, the digest verification, the atomic publication, the per-artifact lock and the idempotent cache |
| `pi_platform/adapters/research/sources.py` | The source-first selection, the bounded reads, the source-map handling and the minified-bundle labelling |
| `pi_platform/adapters/research/tooling.py` | The optional tooling matrix, the Python bytecode disassembly with the version gate and the allowlisted Java decompiler with its constrained invocation |
| `pi_platform/core/research/policy.py` | `allowed_hosts` on the acquisition policy |
| `pyproject.toml`, `distribution/licenses/*` | The optional `node` extra and the licence records of the two grammars |

### Commands and results

```bash
python3 -m unittest tests.test_dependency_artifacts -v
# Ran 35 tests -- OK
```

### Unresolved limitations

* **NOT RUN** -- a download against a real registry. Every
  acquisition test uses a deterministic fetcher, so the policy, the
  integrity check, the cache and the concurrency are covered offline;
  the live registry interaction is not.
* **NOT RUN** -- a real Java decompiler. The invocation contract is
  proven with a stub executable; no decompiler is bundled, so the
  "class-only dependency" scenario is exercised through the stub and
  through the missing-tool path, not through a real decompiler.
* **NOT RUN** -- the container and venv profiles with the optional
  tools installed. The `node` extra is not part of `production`, so
  the production image is unchanged by construction.

---

## Slice 4 -- real research through MCP and A2A

### Changes

| File | Change |
|---|---|
| `pi_platform/mcp/tool_schemas.py` | The schemas of `project.dependency_tree/search/read/acquire` and the new Wiki arguments |
| `pi_platform/mcp/server.py` | The four research handlers, the real Maven lookup behind `project.get_dependency` and the typed research errors |
| `pi_platform/mcp/context.py` | `dependency_research` on the tool context and the default context factory |
| `pi_platform/core/a2a/__init__.py` | The versioned research envelope, the allowlist, the dispatch and the rejection of an unknown operation |
| `pi_platform/adapters/research/composition.py` | The production composition of the one service that both transports use |
| `pi_platform/cli/main.py` | The embedded and the standalone composition wire the research service; the agent card advertises the research skill only when it is wired |
| `pi_platform/core/orchestration/capability_discovery.py`, `pi_platform/adapters/orchestration/capability_discovery.py` | The `protocols.dependencyResearch` block derived from the actual wiring |
| `pi_platform/core/orchestration/production_capability_gate.py` | The `dependency-research:evidence` verdict that fails an acknowledgement-only or an echoed-coordinate answer |

### Commands and results

```bash
python3 -m unittest tests.test_mcp_dependency_research -v
# Ran 24 tests -- OK

python3 -m pi_platform.cli.production_capability_gate
# "dependency-research:evidence": PASS
#   "the research capability answers with evidence (status=partial, nodes=100)"
```

### Unresolved limitations

* **NOT RUN** -- the A2A HTTP transport end to end. The dispatch
  core is covered; the HTTP surface is exercised only through the
  existing transport tests.

---

## Slice 5 -- Wiki enrichment and token-conscious reuse

### Changes

| File | Change |
|---|---|
| `pi_platform/core/wiki/llm_wiki.py` | The content revision, the per-page lock, the `expected_revision` precondition, the dependency provenance, the staleness report and the stored/indexed state of a write |
| `pi_platform/mcp/server.py`, `pi_platform/mcp/tool_schemas.py` | `expected_revision`, `dependency_notes` and `inputs` on the Wiki tools |
| `distribution/skills/project-intelligence/SKILL.md`, `references/MCP-TOOLS.md` | The Wiki-first client workflow and the new tool contracts |
| `.ai/wiki/modules/llm-wiki.md`, `.ai/wiki/interfaces/mcp-tools.md` | The shipped behaviour of the enrichment |

### Commands and results

```bash
python3 -m unittest tests.test_wiki_research_enrichment -v
# Ran 16 tests -- OK

python3 scripts/sync_skills.py check
# Local skills: PASS
```

---

## Slice 6 -- user documentation

### Changes

| File | Change |
|---|---|
| `README.md` | Rewritten: 675 words excluding commands and tables, the quick start in the first 40 lines, one diagram with its prose alternative, the use-case and connection tables and the capability matrix |
| `docs/USER_GUIDE.md` | New: the interfaces, their ports, the enabling conditions, the authentication and the first queries |
| `docs/DEPENDENCY_RESEARCH.md` | New: the language and format matrix, the tool arguments, the A2A envelope, the acquisition policy, the reconstruction limits and the Wiki reuse |
| `docs/ARCHITECTURE.md` | New: three focused diagrams with prose and the canonical/disposable distinction |

### Runtime evidence

The container quick start was executed in a clean fixture
(`/tmp/opencode/pe-target`): the kit export, `start.sh` and the
probes `/` 200, `/health` 200, `/health/ready` 200 `{"ready":true}`,
`GET /mcp` 405, `POST /mcp initialize` and `tools/list` 200.

### Unresolved limitations

* **NOT RUN** -- the Windows PowerShell path (no Windows host).
* **NOT RUN** -- the Python virtual-environment fallback: it needs
  the hash-locked production wheel closure and the model download.
* The published GHCR `:dev` kit still carries the pre-change
  Makefile, so the README documents the **current source**, not the
  published image. The gap is a publication matter, not a
  documentation one.
* The `POST /v1/chat/completions` route answered 200 in the probe
  although the README describes it as controlled by
  `PI_OPEN_WEBUI_ADAPTER`. The flag is enabled by default in the
  probed image; the README states the condition, not the default.

---

## Slice 7 -- integration, knowledge maintenance and adoption

### Changes

| File | Change |
|---|---|
| `.ai/wiki/modules/dependency-research.md` | New: the service, the record contract, the limits, the adapters and the boundaries |
| `.ai/wiki/interfaces/dependency-research.md` | New: the MCP and A2A shapes, the errors, the capability discovery and the provenance |
| `.ai/wiki/adr/0031-cross-language-research-tooling-policy.md` | New: the optional-parser and decompiler policy |
| `.ai/wiki/modules/llm-wiki.md`, `.ai/wiki/architecture/portable-deployment.md`, `.ai/wiki/interfaces/mcp-tools.md`, `.ai/wiki/interfaces/a2a.md`, `.ai/wiki/INDEX.md` | The shipped behaviour of the enrichment, the help-first kit, the research tools and the research dispatch |

### Commands and results

```bash
python3 harness.py wiki-validate
# {"ok": true, "documents": 131, "issues": []}

python3 harness.py openspec-check
# Totals: 90 passed, 0 failed (90 items)

openspec validate improve-dependency-research-and-onboarding --strict
# Change 'improve-dependency-research-and-onboarding' is valid
```

---

## Scenario-to-test result table

38 scenarios, 9 deltas. `PASS` means a test in this repository
exercises the scenario. `NOT RUN` means the scenario could not be
executed on this host; the reason is in the last column.

### `2026-10-11-one-click-distribution`

| Scenario | Test | Result |
|---|---|---|
| Bare make is read-only | `DeploymentHelpTests.test_bare_make_is_read_only_without_docker_python_or_env_file` | PASS |
| Command coverage | `DeploymentHelpTests.test_help_describes_every_public_target` | PASS |
| Repeated start | `DeploymentTopologyAcceptanceTests.test_repeated_start_keeps_the_sidecars_and_reports_no_false_orphans`, `…test_a_reduced_helper_topology_is_what_reports_the_sidecars_as_orphans` | PASS |
| Backend transition | `DeploymentTopologyTests.test_every_launcher_compose_call_carries_the_sidecar_topology`, `DeploymentTopologyAcceptanceTests.test_a_genuine_unrelated_service_is_never_removed` | PASS |
| Port from configuration | `DeploymentHelpTests.test_startup_reports_the_port_configured_in_the_env_file`, `…test_the_shell_environment_overrides_the_env_file_port` | PASS |
| Readiness fails | `DeploymentHelpTests.test_a_failed_readiness_never_reports_ready`, `…test_a_failed_make_start_never_reports_ready` | PASS |

### `dependency-research`

| Scenario | Test | Result |
|---|---|---|
| Transitive explanation | `DependencyGraphTests.test_a_transitive_path_is_reported_with_its_why_path`, `PythonEcosystemTests.test_the_uv_lock_projects_the_resolved_closure` | PASS |
| Cycle and budget | `DependencyGraphTests.test_a_cycle_is_visited_once`, `…test_the_node_limit_truncates_and_says_so`, `…test_the_depth_limit_truncates_and_says_so` | PASS |
| Missing lock | `ResearchServiceContractTests.test_a_project_without_dependencies_is_unavailable_not_empty_success`, `PythonEcosystemTests.test_the_declared_constraint_and_the_resolved_version_are_separate_facts` | PASS |
| Offline cache miss | `AcquisitionTests.test_an_offline_miss_is_reported` | PASS |
| Integrity mismatch | `AcquisitionTests.test_an_integrity_failure_never_publishes_the_artifact` | PASS |
| Hostile archive | `ArchiveInspectionTests.test_a_traversal_member_is_rejected`, `…test_an_absolute_member_is_rejected`, `…test_a_symlink_that_escapes_is_rejected`, `…test_an_oversized_member_is_rejected`, `…test_too_many_members_are_rejected`, `…test_a_compression_bomb_is_rejected` | PASS |
| Source preference | `LibraryReadTests.test_the_source_is_preferred_over_the_bytecode` | PASS |
| No recoverable body | `ToolingTests.test_a_native_binary_is_never_decompiled` | PASS |

### `2026-10-26-python-dependency-intelligence`

| Scenario | Test | Result |
|---|---|---|
| Environment-specific Python graph | `PythonEcosystemTests.test_the_uv_lock_projects_the_resolved_closure`, `…test_the_poetry_lock_projects_groups_and_extras`, `…test_the_uv_optional_dependencies_become_optional_edges` | PASS |
| Installed metadata disagreement | `PythonEcosystemTests.test_an_installed_version_that_differs_from_the_lock_is_reported` | PASS |
| Python archive and bytecode fallback | `ToolingTests.test_the_current_bytecode_version_is_read_as_a_disassembly`, `…test_a_bytecode_file_of_another_version_is_unsupported` | PASS |

### `javascript-dependency-intelligence`

| Scenario | Test | Result |
|---|---|---|
| Multiple versions and peers | `NodeEcosystemTests.test_two_versions_of_one_package_stay_distinct`, `…test_a_nested_version_wins_over_the_top_level_one` | PASS |
| Workspace origin | `NodeEcosystemTests.test_a_workspace_package_is_its_own_importer` | PASS |
| Mapped dependency code | `LibraryReadTests.test_a_valid_source_map_with_bodies_is_read`, `…test_a_source_map_without_bodies_reports_the_missing_body`, `…test_an_invalid_source_map_is_reported_as_invalid` | PASS |
| Minified library | `LibraryReadTests.test_a_minified_bundle_is_labelled_generated`, `…test_a_readable_source_is_not_labelled_generated` | PASS |

### `2026-10-04-jar-dependency-intelligence`

| Scenario | Test | Result |
|---|---|---|
| Class-only dependency | `ToolingTests.test_an_allowlisted_decompiler_produces_a_bounded_reconstruction` | PASS (the decompiler is a **stub**: the invocation contract, the bounds and the provenance are proven; a real decompiler is not bundled) |
| Decompiler absent | `ToolingTests.test_a_missing_java_decompiler_is_a_capability_diagnostic`, `…test_a_decompiler_that_is_not_allowlisted_is_refused` | PASS |

### `2026-10-07-mcp-server`

| Scenario | Test | Result |
|---|---|---|
| Tools discovery and execution | `McpDependencyResearchTests.test_the_research_tools_are_advertised`, `…test_the_tree_tool_returns_the_evidence_backed_graph`, `…test_the_tree_tool_honours_the_limits_and_reports_truncation` | PASS |
| Legacy Maven lookup | `McpDependencyResearchTests.test_the_legacy_maven_lookup_answers_with_real_evidence`, `…test_the_legacy_maven_lookup_says_when_the_coordinate_is_absent` | PASS |
| Isolation and errors | `McpDependencyResearchTests.test_the_acquire_tool_is_refused_without_an_approved_source`, `…test_without_a_research_service_the_tools_report_the_missing_capability` | PASS |

### `2026-10-12-a2a-adapter`

| Scenario | Test | Result |
|---|---|---|
| Transport parity | `CrossTransportTests.test_both_transports_answer_the_same_question_with_the_same_evidence` | PASS |
| Disabled research | `A2aDependencyResearchTests.test_a_disabled_surface_rejects_the_research_request`, `…test_a_denied_actor_rejects_the_research_request` | PASS |
| Unsupported operation | `A2aDependencyResearchTests.test_an_unknown_research_operation_is_rejected_not_acknowledged`, `…test_an_unsupported_envelope_version_is_rejected` | PASS |

### `2026-10-25-llm-wiki-curated-knowledge`

| Scenario | Test | Result |
|---|---|---|
| Repeat question | `TwoQuestionScenarioTests.test_the_second_question_researches_nothing` | PASS |
| New insight on existing page | `WikiProvenanceTests.test_unrelated_curated_text_is_preserved`, `…test_a_duplicate_insight_is_not_written_twice`, `WikiPreconditionTests.test_the_conflict_carries_the_current_revision_for_a_merge` | PASS |
| Dependency upgrade | `TwoQuestionScenarioTests.test_a_dependency_upgrade_invalidates_the_curated_evidence`, `WikiProvenanceTests.test_a_changed_dependency_version_makes_the_note_stale` | PASS |
| Concurrent edits | `WikiPreconditionTests.test_a_concurrent_writer_does_not_lose_a_change` | PASS |
| Index failure after write | `WikiSearchabilityTests.test_a_failed_index_refresh_leaves_the_page_stored`, `…test_the_index_refresh_is_idempotent` | PASS |

### `user-onboarding`

| Scenario | Test | Result |
|---|---|---|
| New container user | the live container probe of the quick start (kit export, `start.sh`, `/`, `/health`, `/health/ready`) and the `README.md` quick-start section | PASS |
| Docker unavailable | the `README.md` Python fallback section and `docs/PRODUCTION_INSTALL.md` | **NOT RUN** -- the hash-locked production wheel closure and the model download are not available on this host; the commands are the existing documented ones, verified against the source, not executed |
| Choose an interface | the `README.md` connection table and `docs/USER_GUIDE.md`, verified against the shipped routes in `pi_platform/adapters/ui/http_server.py` | PASS |
| Diagram unavailable | the prose text alternative next to the README diagram and the prose next to every architecture diagram | PASS |

### Environment evidence and open limitations

| Item | State |
|---|---|
| Docker Compose acceptance (real, disposable project) | PASS -- 4 tests |
| Real product image with the real model | **NOT RUN** -- needs the ~310 MB model download and the image pull |
| Windows launcher and PowerShell | **NOT RUN** -- no Windows host, no PowerShell |
| Live registry download | **NOT RUN** -- the acquisition tests use a deterministic fetcher |
| Real Java decompiler | **NOT RUN** -- none is bundled; the stub proves the contract only |
| `scripts/test_deployment_launchers.ps1` | **NOT RUN** -- Windows only |
| The published GHCR `:dev` kit | Pre-dates the help-first change; the publication is out of scope for this change |

---

## Adoption — 2026-10-28

The change was adopted and archived with the installed OpenSpec
workflow:

```bash
openspec archive improve-dependency-research-and-onboarding --yes
# Change 'improve-dependency-research-and-onboarding' archived as
# '2026-10-28-improve-dependency-research-and-onboarding'.
```

- The six existing capability identities were preserved; their
  dated spec directories were updated in place.
- The three new capabilities were created with the first-acceptance
  date: `2026-10-28-dependency-research`,
  `2026-10-28-javascript-dependency-intelligence` and
  `2026-10-28-user-onboarding`. Their placeholder `## Purpose`
  section was replaced with the real purpose of each capability.
- `openspec/CURRENT.md` lists each of the three new capabilities
  exactly once, next to the related ones, and records the adoption
  in a dated section.
- `openspec validate --all --strict` reports 92 passed, 0 failed.

The verification state of the adoption itself is the state recorded
above: every scenario has an explicit PASS or an explicit NOT RUN
with its reason. The NOT RUN items are environment limits, not
unverified claims.

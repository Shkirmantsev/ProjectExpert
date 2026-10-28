# Tasks

All boxes start unchecked: these are implementation tasks, not planning accomplishments. Execute in order; each numbered section is a reviewable slice. After each material step, checkpoint files, evidence, decisions and the next action. Read [handoff](handoff.md) first.

## 1. Establish acceptance fixtures and deployment regression

- [x] 1.1 Resume or start the implementation session using the handoff commands; inspect drift and overlapping active changes. Record tested image/kit digest, host and fixture revision.
- [x] 1.2 Add a failing bare-make/help test in `tests/test_portable_deployment.py` or adjacent launcher tests: no Docker/Python/env file, same command list, descriptions and no mutation.
- [x] 1.3 Change only exported-kit default/help descriptions; preserve explicit start targets and script behavior. Verify exported bundle has the updated Makefile.
- [x] 1.4 Reproduce repeated-start warning in a disposable Compose project; trace helper file sets and service identity. Fix Bash and PowerShell topology consistently; do not mask stderr or delete orphans.
- [x] 1.5 Add focused helper invocation, genuine-orphan, CPU/GPU fallback, model-setup completion, failed readiness and env-file/custom-port precedence regressions. Run existing portable deployment and inference launcher tests; real Docker repeated-start acceptance must also pass before runtime claims.
- [x] 1.6 Update kit operations and troubleshooting with explicit startup/help migration and record verification evidence.

## 2. Shared dependency research contract and offline graph

- [x] 2.1 Implement records, result status/completeness, evidence references, budgets, snapshot-bound cursors and service port from design. Add deterministic graph fixtures for transitive paths, cycles, multiple versions, missing locks and truncated traversal.
- [x] 2.2 Connect Java/Python existing evidence to the shared service without replacing existing ingestion; test declarations versus resolved versions and project-bound references.
- [x] 2.3 Add Python uv/Poetry supported-version lock readers and explicitly selected installed-metadata reads. Fixtures cover extras, markers, groups, editable/workspace origins, mismatches and unknown format versions. Assert no imports/install/network calls.
- [x] 2.4 Select and document a static Node parser and exact supported npm/pnpm/Yarn lock versions. Add package/workspace/peer/optional/dev/alias/multiple-version fixtures, JS/TS symbols, imports/reexports and declarations. Record parser licensing and packaging impact.
- [x] 2.5 Wire lock/source families into existing registry/discovery/pipeline. Keep node_modules/.venv/binary broad exclusions; prove targeted package evidence becomes searchable and unchanged artifacts reuse cached parse results.

## 3. Artifact acquisition and library implementation evidence

- [x] 3.1 Add explicit policy-controlled acquisition with exact identities, approved sources, redirect/integrity checks and resource bounds. Test offline miss, denial, integrity failure, timeout, concurrent requests and idempotent cache reuse.
- [x] 3.2 Inspect bounded wheel/source archive/JAR/Node package contents safely. Cover traversal, symlink/hardlink escape, oversized members/expansion and sensitive source policy. Never invoke install scripts or target code.
- [x] 3.3 Implement source-first selection and bounded symbol/code reads with hashes, paths, lines and representation labels. Cover matching/mismatching source artifacts, valid/invalid source maps and missing source bodies.
- [x] 3.4 Evaluate and pin optional Java decompiler and Python bytecode tooling only after version/license/isolation review. Add supported fixture evidence and missing-tool/unsupported-version fallback tests. Do not certify native binary decompilation.
- [x] 3.5 Package chosen optional tools deliberately, update affected production locks/SBOM/license records and capability diagnostics, and test the installed container and venv profiles. Record exact support matrix.

## 4. Real research through MCP and A2A

- [x] 4.1 Add proposed MCP tree/search/read/acquire schemas and handlers backed by the shared service; replace Maven lookup placeholder while retaining legacy inputs. Validate arguments, limits, readiness and policy.
- [x] 4.2 Add A2A allowlisted research envelope/dispatch and JSON artifacts; wire service in embedded and standalone composition. Preserve flags/auth and legacy non-research behavior; unknown research cannot succeed as ack.
- [x] 4.3 Run MCP initialize/tools-list/call and equivalent A2A requests against the same fixture; compare semantic results, not transport wrappers. Include disabled/denied/unsupported/timeout, cross-project evidence, stale cursor and excessive-budget cases.
- [x] 4.4 Update capability discovery and agent-card skills from actual wiring. Extend production capability tests to fail on acknowledgement-only or echoed-coordinate “success.”

## 5. Wiki enrichment and token-conscious reuse

- [x] 5.1 Extend Wiki read/write responses and schema with content revision/precondition for research enrichment. Add lock-protected conflict tests while retaining OKF, path, atomic write and audit behavior.
- [x] 5.2 Store dependency provenance and fact/inference labels; detect input hash/version changes as stale. Preserve unrelated curated text; test duplicate insight and concurrent writer behavior.
- [x] 5.3 Integrate existing index refresh; report stored versus indexed state and retry failure idempotently. Prove a curated dependency explanation appears in normal project.search after refresh and survives restart.
- [x] 5.4 Update canonical client workflow instructions: Wiki-first, bounded evidence requests, enrich matching page, validate and confirm index state. Regenerate owned bundles if required; do not edit generated outputs alone.
- [x] 5.5 Run a two-question scenario: first question researches and curates; repeat reuses fresh Wiki evidence with zero extra acquire/decompile calls; dependency upgrade invalidates that evidence and triggers targeted renewal. Record tool counts and response bytes, not invented token percentages.

## 6. User documentation and big-picture navigation

- [x] 6.1 Implement [README blueprint](readme-blueprint.md) with verified present-tense capability claims, Docker setup/run first, venv fallback and short use-case/configuration tables. Remove stale phase prose from the user entry point.
- [x] 6.2 Create expanded user, architecture and dependency research guides; include architecture, user workflow and data lifecycle diagrams with prose alternatives. Link existing installation/configuration/kit references without duplicating them.
- [x] 6.3 Verify every displayed endpoint, port, flag and auth instruction from actual startup composition. Resolve the Open WebUI listener/shim distinction and A2A enabled/disabled behavior before publishing examples.
- [x] 6.4 Execute quick-start commands in clean disposable target fixtures, including a path with spaces, container setup/run, readiness, stop and venv startup. Test upgrade preservation and custom port. Record unsupported/unavailable host checks as NOT RUN.
- [x] 6.5 Review README against the 600–900 word target, visible quick start, explained terminology, one small home-page diagram and link integrity. Conduct a task walkthrough: a reader can choose setup, find UI, connect an agent and find configuration without architecture knowledge.

## 7. Integration, knowledge maintenance and adoption

- [x] 7.1 Apply [context-impact](context-impact.md) only for verified behavior, preserving stable IDs; refresh the local Wiki index. Record durable parser/decompiler decisions in an ADR if warranted.
- [x] 7.2 Run the focused suites in the handoff and new scenario tests, then `python harness.py check`. Review the full diff, generated artifacts, dependency/license changes and absence of unrelated edits.
- [x] 7.3 Validate all nine deltas using `python harness.py openspec-check` and `openspec validate improve-dependency-research-and-onboarding --strict`; attach a scenario-to-test result table with PASS/FAIL/NOT RUN and environment evidence.
- [x] 7.4 Verify container acceptance separately from unit/schema checks. Keep hardware/platform/publication evidence in overlapping changes accurate; no silent transfer of completion claims.
- [x] 7.5 After implementation acceptance, adopt deltas preserving existing identities and assigning first-Git-acceptance dates to new capabilities, update openspec/CURRENT.md exactly once per capability, and archive via installed workflow. Do not archive partial implementation.
- [x] 7.6 Checkpoint final status, completed tasks, remaining blockers and exact verification; leave a short next-agent handoff if anything remains. Do not mark the implementation complete merely because this plan exists.

## Requirement-to-slice map

| Spec delta | Tasks | Required proof |
|---|---|---|
| one-click-distribution | 1 | Help without dependencies; real repeated startup; correct URL |
| dependency-research | 2–3 | Exact evidence/partial graph, safe bounded artifacts and code |
| python-dependency-intelligence | 2.3, 3 | Environment-sensitive locks and source/bytecode fallback |
| javascript-dependency-intelligence | 2.4–2.5, 3 | Workspace/peer graphs and source/API evidence |
| jar-dependency-intelligence | 2.2, 3.3–3.4 | Source preference, reconstructed bodies and graceful fallback |
| mcp-server | 4 | Real protocol calls and legacy Maven compatibility |
| a2a-adapter | 4 | Research artifacts match MCP; no fake completed ack |
| llm-wiki-curated-knowledge | 5 | Conflict-safe reuse, freshness and searchable enrichment |
| user-onboarding | 6 | Clean setup walkthrough, accurate interfaces and linked diagrams |

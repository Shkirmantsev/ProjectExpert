---
id: glossary.platform
title: Platform Glossary
kind: glossary
status: active
summary: Vocabulary used by the v0.8 Project Intelligence Platform.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md
  - openspec/changes/plan-v0-8-platform-architecture/proposal.md
  - openspec/changes/implement-phase-1-foundation/design.md
  - pi_platform/core/canonical/value_types.py
  - pi_platform/core/sync/policy_stub.py
  - pi_platform/core/sync/project_lock.py
  - pi_platform/core/sync/wal.py
maintenance:
  mode: authored
related:
  - glossary.domain
---

# Platform Glossary

## Canonical knowledge

Git-versioned, deterministic, content-addressable knowledge that
forms the durable source of truth for the platform. Stored under
`project-knowledge/`. Examples: chunks, entities, relations,
manifests, OKF Wiki pages.

## Runtime working knowledge

Optimised operational representation of the project used at runtime.
Stored under `.project-intelligence-cache/`. Includes dense vectors,
sparse/BM25 index, graph index, embeddings cache, model cache,
working-tree overlay. Never committed to Git.

## Hydration

The operation that loads canonical knowledge into the runtime
working knowledge store. Driven by manifests. Reuses cached
embeddings where content hashes match.

## Materialisation

The operation that turns selected runtime changes into durable
canonical knowledge. Requires operator/operator-approval-gated commit.
Never includes runtime binary artefacts.

## Working-tree overlay

The transient representation of uncommitted changes (modified,
added, deleted, untracked) applied to the runtime working knowledge
store. Never written to durable canonical knowledge without an
explicit materialisation step.

## Content addressing

Storage keyed by the SHA-256 digest of the canonical serialization
of an input. Enables cache reuse across branches and across
repeated ingests.

## Knowledge state

The provenance state of a durable fact: `verified`, `inferred`,
`assumption`, `conflicting`, `stale`, `unknown`. Phase 1 ships
the `KnowledgeState` enum in
[`pi_platform.core.canonical.value_types`](../../../pi_platform/core/canonical/value_types.py).

## Policy decision

Returned by the Phase 1 `PolicyDecisionStub.decide(action, target)`
contract:

- `ALLOW` — proceed;
- `DENY` — refuse;
- `REQUIRE_APPROVAL` — wait for an explicit operator token.

The default behaviour is `ALLOW` for `hydrate`/`reconcile` and
`REQUIRE_APPROVAL` for `materialise`; the full central Policy
Engine arrives in Phase 7.

## Project lock

The Phase 1 per-project advisory file lock implemented by
`pi_platform.core.sync.project_lock.ProjectLock`. The lock file
lives at `tmp/local/project-locks/<project-id>.lock`. The product
does NOT import `scripts/file_lock.py`; the implementation
duplicates the cross-platform `fcntl` / `msvcrt` semantics so
the harness lock files and the product lock files can coexist.

## Write-ahead log

The `pi_platform.core.sync.wal.WriteAheadLog` records one JSON
line per materialise operation. The `materialise_in_progress`
marker is created at the beginning of a materialise and removed
at commit; on startup, recovery rolls back to the last committed
entry when the marker is present, otherwise the WAL is
truncated.

## OKF

Open Knowledge Format. The platform's Wiki layer targets OKF v0.2.
Platform-specific extensions use the `pi_` prefix.

## OKF adapter

The internal component that translates between the internal
Knowledge Model and the configured OKF profile/version. Decouples
the internal model from OKF revisions.

## Capability

A fine-grained authorisation unit, e.g. `knowledge.read`,
`knowledge.write`, `knowledge.materialize`, `retrieval.query`,
`retrieval.admin`, `graph.read`, `graph.write`, `source.read`,
`source.import`, `filesystem.read`, `filesystem.write`, `git.read`,
`git.write`, `config.read`, `config.write`, `secret.reference`,
`secret.resolve`, `mcp.invoke`, `mcp.admin`, `agent.delegate`,
`network.local`, `network.external`, `audit.read`, `audit.write`.

## Hook

A managed, time-bounded, failure-policy-aware extension invocation on a
documented lifecycle event (e.g. `beforeMcpTool`,
`afterRetrieval`, `beforeMaterialization`).

## Plugin

A packaged extension registered through the plugin registry. Has
its own license, version, capabilities, hooks and configuration.

## Feature flag

A scoped toggle that can be `disabled`, `enabled`, `experimental`
or `deprecated`. Scoped by machine / project / branch / user /
deployment profile.

## Secret reference

An indirect reference to a secret (e.g. `secret://local/confluence-
token`, `env://HTTP_PROXY`) resolved at runtime by a `SecretProvider`
port. Never serialised into Git knowledge or logs.

## Control plane

The UI/CLI/automation layer for administration, configuration,
policies, permissions, plugin/feature lifecycle, hooks, secret
references, environment mappings, diagnostics, audit, health.

## Data plane

The ingestion, indexing, retrieval, graph, context assembly,
MCP tool execution, A2A request and runtime agent layer.

## Policy engine

The central component that resolves identity + role + requested
operation + resource + project/version context into `ALLOW`,
`DENY` or `REQUIRE_APPROVAL`. Phase 1 ships a stub
(`PolicyDecisionStub`) so the materialise approval gate has a
contract; the full engine arrives in Phase 7.

## License gate

The build-blocking CI gate that fails a release when a
dependency lacks an SPDX identifier, matches a deny pattern or
appears on the review list without an operator acceptance
token. Wired as `make license-gate TARGET=<repo>`.

## Model license

A model-weight license tracked separately from library licenses
in `distribution/licenses/model-licenses.json`. Phase 1 ships
the `ModelLicenseInventory` record type and the save / load
helpers.

## SBOM

A Software Bill of Materials emitted under `distribution/sbom/`
in SPDX-2.3-compatible JSON. Phase 1 ships
`pi_platform.core.licensing.sbom.emit_spdx_sbom`.

## ANN graph

A nearest-neighbour index structure such as HNSW or IVF used for
efficient vector similarity search. Distinct from the knowledge
graph.

## Knowledge graph

The explicit project semantic graph (requirements, components,
classes, methods, etc.) with edges such as IMPLEMENTS, SATISFIES,
DEPENDS_ON, CALLS, USES, IMPLEMENTED_BY, DEFINED_BY, PART_OF,
DOCUMENTED_BY, TESTED_BY, REFERENCES, SUPERSEDES, DESCRIBES.

## MCP

Model Context Protocol. Primary interface by which coding agents
access platform tools and context.

## A2A

Agent-to-Agent protocol. Used for agent-to-agent task
collaboration. Complementary to MCP, not a substitute.

## Retrieval-first policy

The escalation order from §33: exact/sparse lookup → dense
semantic → hybrid fusion → graph + hierarchy → rerank →
bounded Context Assembly → LLM reasoning over selected context
→ raw source scan only when retrieval evidence is insufficient.

## Phase 2 ingestion

The [ingestion module](../modules/ingest.md) implements PipelineDriver, source adapters,
structural chunking, layered enrichment, content-address reuse and inbox policies.
SourcePromotionPolicy distinguishes LOCAL_ONLY, REFERENCE and SNAPSHOT; parser
subprocesses and cache records carry explicit provenance. See the
[source interface](../interfaces/source-adapters.md), [chunker](../interfaces/chunker.md)
and [enrichment](../interfaces/enrichment.md) contracts. Persistent storage and retrieval
remain future phases.

## Phase 3 runtime store

The [runtime store module](../modules/runtime-store.md) fills in the Phase 1 placeholder
runtime cache: per-shard content-addressed cache, version stamp, write-ahead log,
per-project advisory file lock. The default backend uses SQLite (stdlib `sqlite3`)
through [`RuntimeStorePort`](../interfaces/runtime-store.md); PostgreSQL is opt-in for
the enterprise-scale profile (gated on `storage.backend: postgres` plus a `LicenseGate`
pass for the `psycopg` Apache-2.0 driver). Phase 3 also adds the three indexes
(`SparseIndexPort`, `DenseIndexPort`, `FullTextIndexPort`), the sharded graph
(`GraphPort`), the `GraphExpansion` preview port, the `ProvenancePort` state machine
and the `FreshnessTrackerPort` snapshot.

## Phase 3 sharded graph

The [graph module](../modules/graph.md) implements the canonical knowledge graph with
hash-prefix shards (§10.1, §16, §17). Every entity body is stored by its SHA-256
content address under `objects/<prefix>/<hash>.json` so identical entity bodies across
branches share one canonical artefact. The 50 000-entity property test
(`tests/test_graph_50k.py`) asserts both the shard count distribution and the
32 MiB per-file cap. ANN vectors and the canonical knowledge graph are kept strictly
separate (§17 invariant).

## Phase 4 retrieval pipeline

The [retrieval module](../modules/retrieval.md) composes the Phase 3 storage layer and
the §25 embedding model into the seven-stage §29 multi-stage pipeline. The pipeline
implements the §33 retrieval-first escalation policy (exact → sparse → dense → hybrid →
graph → hierarchy → rerank → bounded context). Per-stage telemetry
(`candidatesIn`, `candidatesOut`, `durationMs`, `budgetExhausted`) feeds the §49
evaluation fixture.

## EmbeddingModelPort

The `EmbeddingModelPort` is the §25 abstract embedding port. It exposes a
multilingual, CPU-capable, replaceable, commercially-licensed embedding backend
through `embed`, `embed_batch`, `dimension`, `model_version`, `license_id` and
`stats` operations. The default adapter is the stdlib-only
`HashingEmbeddingAdapter`; the opt-in adapter is the
`MultilingualSentenceTransformerEmbeddingModel` (Apache-2.0 weights + runtime).
See [ADR 0009](../adr/0009-embedding-model-selection.md).

## HybridRetrievalPort

The `HybridRetrievalPort` is the §27 abstract hybrid retrieval port. It composes
the dense ANN, the sparse BM25 and the exact-identifier lookup behind a single
ranked candidate set. The `RetrievalHit` value type is the lingua-franca record
exchanged across every Phase 4 stage. The default fusion strategy is
reciprocal rank fusion (RRF) with `k=60`; the linear weighted sum is the
documented fallback. See [ADR 0010](../adr/0010-hybrid-fusion-strategy.md).

## RerankerPort

The `RerankerPort` is the §30 abstract pluggable reranker port. The cross-encoder
(`cross-encoder/ms-marco-MiniLM-L-6-v2`, MIT) is the documented default; the
BM25-light (Apache-2.0) is the stdlib fallback; the ColBERT-style late-interaction
reranker (MIT) is the optional opt-in. Rerankers operate on bounded candidate
sets only; the multi-stage pipeline enforces a `rerankBudget` cap.

## MetadataFilter / MetadataFilterPort

The `MetadataFilter` value type and the `MetadataFilterPort` port enforce the §24
temporal validity rule (`validFrom <= queryDate AND (validTo IS NULL OR
validTo >= queryDate)`), the project-version filter, the §56
security-classification allow-list and the language / domain / module /
requirement filters. The drop reasons appear in the documented evaluation order
(`temporal_invalid`, `version_mismatch`, `security_denied`, `language_mismatch`,
`domain_mismatch`, `module_mismatch`, `requirement_mismatch`).

## ContextAssemblerPort

The `ContextAssemblerPort` is the §32 abstract port that builds a bounded
context bundle from the multi-stage retrieval pipeline output. The bundle
deduplicates overlapping evidence, enforces the `ContextBudget`, preserves
`Citation` records, prefers authoritative evidence, surfaces conflicts and
flags uncertain hits. The bundle is the language-passport contract between
the Phase 4 retrieval pipeline and the Phase 5 orchestrator / Phase 6 MCP
server.

## Retrieval benchmark fixture

The `retrieval-benchmark` capability is the §49 evaluation fixture contract.
The fixture exercises the multi-stage pipeline against a deterministic 1 000+-
chunk / 100+-entity corpus with 100+ labelled queries, recording recall,
precision, MRR, latency, cache reuse, branch-switch hydration time,
stale-knowledge detection and plugin setup success rate. The fixture contract
ships as the `tests/test_retrieval_benchmark.py` test module.

## Phase 4 production graph expansion

The Phase 3 `graph-expansion` preview port is closed by the Phase 4
`ProductionGraphExpansion` adapter (in
`pi_platform/adapters/runtime/graph_expansion.py`). The production adapter
walks the Phase 3 `GraphPort` (NOT the ANN graph), enforces `hops`,
`edge_types` and `budget` parameters and applies the documented default
edge-type set per §31. The Phase 3 stub
`BoundedGraphExpansion` remains available for Phase 3 regression tests.

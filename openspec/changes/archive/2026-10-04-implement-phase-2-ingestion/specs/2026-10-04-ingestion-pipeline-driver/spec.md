# ingestion-pipeline-driver Specification delta

Covers architecture section §18 (Ingestion Pipeline) and §13
(content-addressed processing across branches). Defines the
`PipelineDriver` coordinator that runs the documented
parsers → chunking → enrichment → graph/vector/metadata → runtime
store pipeline, plus the per-stage error-handling, idempotency and
cancellation contract.

The Phase 1 `canonical-knowledge-schema`, `git-version-aware-runtime`
and `bidirectional-canonical-runtime-sync` capabilities provide the
underlying value types and version identity that this spec builds on.

## ADDED Requirements

### Requirement: PipelineDriver stage sequence

The platform MUST expose a `PipelineDriver` coordinator that runs the
ingestion pipeline as an ordered sequence of stages:

1. **Source parsing** — a `SourceAdapter` (see
   `document-source-adapters`, `structured-code-intelligence`,
   `jar-dependency-intelligence`, `openspec-change-adapter`) produces
   a `Document` plus zero or more `Section` records from a `Source`;
2. **Semantic / structural chunking** — a `Chunker` (see
   `semantic-structural-chunking`) splits the document into
   `Chunk` records with parent links preserved;
3. **Context enrichment** — a `ContextEnricher` (see
   `context-enrichment`) attaches the three-layer context and
   produces `ContextualChunk` records;
4. **Graph / vector / metadata emission** — the driver emits entities,
   relations and metadata into the canonical knowledge graph via the
   Phase 3 graph port (out of scope here) and writes the chunk and
   entity records to the runtime working knowledge store via the
   Phase 3 `RuntimeStore` port (out of scope here);
5. **Runtime store update** — the driver hands the resulting
   `Chunk`, `ContextualChunk`, `Entity`, `Relation` and `Evidence`
   records to the runtime cache (Phase 3 owns the persistent index).

The driver MUST accept the `Source`, `ProjectVersion` and
`WorkingTreeOverlay` produced by the Phase 1 Git module and MUST write
a SHA-256 content address for every durable chunk before handing it
to the runtime store so that the Phase 3 store can deduplicate across
branches (see `content-addressed-processing`).

#### Scenario: driver runs the documented five stages

Given a `MarkdownAdapter` (covered by `document-source-adapters`) and a
`Source` referencing a Markdown document under
`tmp/local/source/example.md` with policy `LOCAL_ONLY`
When the driver is invoked with that source
Then the driver invokes the parser and produces one `Document` plus
its `Section` records
And the driver invokes the `Chunker` and produces the chunk records
And the driver invokes the `ContextEnricher` and produces the
`ContextualChunk` records
And the driver emits the resulting records to the runtime store
And the driver reports a stage-by-stage transition trace that lists
the source id, the parser used, the chunker used, the enricher used,
the resulting chunk count, the resulting entity count and the
resulting SHA-256 content addresses.

### Requirement: explicit stage error handling

Each stage MUST catch exceptions raised by the next stage, classify them
into one of three categories — `transient`, `permanent`,
`configuration_error` — and propagate them according to the following
configuration rule:

- `transient` errors (network timeouts, advisory lock contention, WAL
  flush failures) MUST be retried at most three times with exponential
  back-off bounded by a stage-specific timeout and surface the final
  error to the caller if all retries fail;
- `permanent` errors (binary file passed to a text parser, parse
  error after recovery exhausted, unsupported content family) MUST
  abort the pipeline immediately, mark the source as
  `KnowledgeState.UNKNOWN` and continue with the next source;
- `configuration_error` errors (missing required field in
  `project-context.yaml`, license gate failure on a newly added
  dependency, broken adapter registration) MUST abort the pipeline
  immediately and refuse to continue with the next source.

The driver MUST log the stage name, source id, attempt count and
final classification so an operator can reconstruct the failure from
the operational log.

#### Scenario: permanent parse error skips the source

Given a `MarkdownAdapter` invoked on a source whose first 16 KiB
contain a NUL byte
When the parser raises a `permanent` parse error
Then the driver marks the source as `KnowledgeState.UNKNOWN`
And the driver continues with the next queued source
And the driver records a stage-error event in the operational log
naming the stage, the source id, the error category and the error
message.

#### Scenario: transient lock timeout retries

Given a source whose first stage attempts to acquire the per-project
advisory file lock and finds it held by another process
When the lock acquisition raises a `transient` timeout error
Then the driver retries the lock acquisition at most three times
And the driver reports the attempt count in the operational log
And the driver surfaces the final error if the third retry fails.

### Requirement: per-stage idempotency

Each stage MUST be re-runnable for the same `(source, projectVersion)`
pair without producing duplicate durable facts. The driver MUST:

- use the SHA-256 content address as the cache key for every chunk
  and entity produced by a stage;
- skip a stage's work entirely when the resulting content address is
  already present in the runtime cache for the same project version;
- preserve the chunk `parentId`/`childIds` invariant validated by
  `tests/test_canonical_roundtrip.py` so a re-run produces a byte-
  identical canonical chunk body for unchanged content.

#### Scenario: re-running the driver skips unchanged chunks

Given a first driver run over `Source` `s-1` that produced chunk `c-1`
with content address `sha-256:A`
When the driver is invoked again on the same `Source` and project
version
Then the driver does not invoke the chunker on `s-1`
And the driver reports `c-1` as a cache hit
And the runtime cache still holds exactly one chunk body for
`sha-256:A`.

### Requirement: cancel propagation

The driver MUST observe a `CancellationToken` and propagate it to
every stage. Cancellation MUST:

- abort the current source as `transient` with category
  `cancelled`;
- flush any in-progress chunk record to the runtime cache before
  returning;
- emit a final operational log event naming the source id, the stage
  that observed the cancellation and the partial chunk count.

#### Scenario: cancel stops the pipeline cleanly

Given a driver run that is mid-way through the chunking stage for
`Source` `s-2`
When the cancellation token is set
Then the driver flushes the chunks produced so far for `s-2` to the
runtime cache
And the driver records a stage-error event with category
`cancelled`
And the driver returns without invoking the next source.

### Requirement: stage instrumentation report

The driver MUST expose a `PipelineReport` value type that records
the per-source stage outcomes. The report MUST contain at minimum:

- `projectVersion: ProjectVersion`;
- `sources: Sequence[Source]` (the sources processed);
- `stages: Sequence[StageOutcome]` where `StageOutcome` records
  `sourceId`, `stage` (`parse` | `chunk` | `enrich` | `emit` |
  `store`), `outcome` (`ok` | `skipped` | `failed`) and
  `contentAddresses: Sequence[str]`;
- `chunkCount`, `entityCount`, `relationCount` totals;
- `cacheHitCount`, `cacheMissCount`;
- `startedAt`, `finishedAt` as ISO-8601 strings.

#### Scenario: report records every stage outcome

Given a driver run over two sources where the second source's
chunker stage returned `failed`
When the driver finishes
Then the report contains one `StageOutcome` per `(source, stage)`
pair
And the `StageOutcome` for the failed chunker records
`outcome="failed"` and the error message
And the report totals match the per-stage totals.

### Requirement: pipeline driver ports

The platform MUST expose the driver behind a `PipelineDriverPort`
abstract class in `pi_platform/ports/ingest/pipeline_driver.py` and
MUST ship a default `LocalPipelineDriver` adapter in
`pi_platform/adapters/ingest/local_pipeline_driver.py`. The default
adapter MUST compose the adapters listed under
`document-source-adapters`, `structured-code-intelligence`,
`jar-dependency-intelligence`, `openspec-change-adapter`,
`semantic-structural-chunking` and `context-enrichment` so that a
caller wires the driver without instantiating internal stage classes.

#### Scenario: driver port is satisfiable by an alternate adapter

Given a test that substitutes the default `LocalPipelineDriver` with
a stub adapter that records every stage call
When the test invokes the driver port against a single `Source`
Then the stub adapter receives exactly one call per stage in the
documented order
And the stub adapter's recorded call sequence matches the scenario
`driver runs the documented five stages`.

## Phase 2 task coverage

The change lists Phase 2 task 45 (`PipelineDriver` implementation) and
the partial scenarios from tasks 56 (`local-source-inbox`),
57 (`content-addressed-processing`) and 58
(`semantic-structural-chunking`, `context-enrichment`,
`document-source-adapters`, `openspec-change-adapter`,
`structured-code-intelligence`, `jar-dependency-intelligence`) that
this capability exercises.

Out of scope:

- the runtime DB rebuild for storage (Phase 3 task 62);
- the sharded knowledge graph (`platform.runtime.Graph`, Phase 3
  task 66);
- the MCP server exposing the pipeline report (Phase 6 task 85);
- the Wiki materialisation of the pipeline entities (Phase 9 task
  112).
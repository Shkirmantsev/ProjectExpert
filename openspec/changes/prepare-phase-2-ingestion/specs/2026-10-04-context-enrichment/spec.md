# context-enrichment Specification delta

Covers architecture section §22 (Context Enrichment) and the
provenance / freshness invariants §54 (Knowledge Provenance) and §55
(Knowledge Freshness). Defines the `ContextEnricher` that emits the
three-layer enrichment (deterministic metadata + domain rules +
optional small LLM) and the `ContextualChunk` record.

The Phase 1 `canonical-knowledge-schema` capability defines the
`Metadata` value type and the `ContextualChunk` value type with the
`chunk` + `contextPrefix` fields; this spec defines the three-layer
enrichment that populates them. The Phase 1
`canonical-knowledge-schema` already covers §23 metadata fields; this
spec adds the §22 deterministic + domain-rule + optional LLM layers.

## ADDED Requirements

### Requirement: ContextEnricher port

The platform MUST expose a `ContextEnricherPort` in
`pi_platform/ports/ingest/context_enricher.py`. Every enricher MUST
implement this port and MUST accept a `Chunk`, the enclosing
`Document` and the active `Source` plus `ProjectVersion`. The
enricher MUST return a `ContextualChunk` whose `chunk` carries the
enriched `metadata` and whose `contextPrefix` carries the
deterministic contextual text.

#### Scenario: ContextEnricher returns a ContextualChunk

Given a `Chunk` from a Markdown document with `metadata.heading="Section A"`
When the `ContextEnricher` is invoked
Then the returned `ContextualChunk.chunk.metadata.section` is
`"Section A"`
And the returned `ContextualChunk.contextPrefix` is the documented
deterministic prefix (heading hierarchy + source path + requirement
ID when available).

### Requirement: deterministic metadata layer

The deterministic layer MUST populate the Phase 1 `Metadata` value
type with every documented §23 field whose value can be derived
deterministically from the source bytes:

- `documentId` — the `Document.id`;
- `version` — the `Source` content version (typically the file's
  modification time recorded as ISO-8601 UTC; never the current
  wall-clock time of the enricher run);
- `language` — the content family (`markdown`, `html`,
  `java`, `java_bytecode`, `openapi`, ...);
- `section` — the enclosing `Section.heading`;
- `module` — the documented module name (Maven module, package or
  namespace) when present;
- `className` — the documented class or component name when present;
- `requirementId` — the documented requirement identifier when the
  chunker tagged the chunk with one;
- `validFrom` / `validTo` — the documented validity dates when
  present in the source;
- `gitCommit` — the active `ProjectVersion.gitHead`;
- `sourcePath` — the `Source.uri`;
- `page` / `line` — the source-derived page or line number when
  present;
- `contentHash` — the SHA-256 hex digest of the canonical chunk
  body.

The deterministic layer MUST NOT generate authoritative identifiers,
versions, dates or security classifications on its own; values are
derived from the source bytes, the source metadata or
`project-context.yaml`.

#### Scenario: deterministic layer fills source-derived fields

Given a Markdown chunk whose source file declares a
`<!-- requirement: REQ-123 -->` directive
When the deterministic layer runs
Then the resulting `Metadata` carries `requirementId="REQ-123"` and
`sourcePath=<Source.uri>` and `contentHash=<sha256>`
And no field carries an invented identifier.

### Requirement: domain-rule layer

The domain-rule layer MUST apply the documented ontology rules
(see §22.2 and the `project-context.yaml:ingest.domainRules`
section) to the deterministic `Metadata`. The layer is a sequence
of deterministic rules that transform or augment `Metadata` fields;
each rule MUST be documented in `project-context.yaml` and MUST NOT
introduce volatile fields.

The default rules the platform MUST support:

- a path-glob rule (`path psb/packing/**`) that sets
  `businessDomain` and `system` from the rule's YAML body;
- an entity-fingerprint rule that emits a `candidateEntities` list
  on `metadata` (the list is `KnowledgeState.ASSUMPTION` until a
  human operator approves it; the rule MUST NOT mark entities as
  `VERIFIED`).

#### Scenario: domain rule sets businessDomain

Given a chunk whose source path matches `psb/packing/**` and a
domain-rule entry mapping the glob to `businessDomain=PACKING`
When the domain-rule layer runs
Then the resulting `Metadata.businessDomain` is `"PACKING"`
And the rule invocation is recorded in operational log
And the chunk's `Evidence.knowledgeState` for the rule output is
`ASSUMPTION` until a human operator approves it.

### Requirement: optional small LLM layer

The optional small LLM layer (see §22.3) MAY be enabled when the
target project configures a `LocalLLMPort` (the Phase 5
`LocalLLMPort` is the binding). When enabled, the layer MUST:

- invoke the local LLM with a documented prompt that requests:
  (a) a concise semantic `contextPrefix`,
  (b) candidate entity mentions,
  (c) candidate relation mentions;
- never invoke a remote / cloud LLM in this Phase 2 capability;
- never authoritatively populate `documentId`, `version`,
  `requirementId`, `validFrom`, `validTo`, `gitCommit`, `sourcePath`,
  `page`, `line`, `securityClassification` or `contentHash`; the LLM
  output is treated as `KnowledgeState.ASSUMPTION` and recorded in
  `ContextualChunk.metadata` under a `pi_assumption` block;
- never write secrets or confidential source content into the LLM
  prompt unless the source is `REFERENCE` or `LOCAL_ONLY` and the
  target `SourcePromotionPolicy` explicitly permits it;
- be disabled by default (the default `project-context.yaml` MUST
  NOT enable the LLM layer).

#### Scenario: LLM layer is disabled by default

Given a fresh `project-context.yaml` produced by `init-project`
When the enricher is invoked
Then the LLM layer is disabled and the enricher returns the
deterministic + domain-rule `ContextualChunk` only.

#### Scenario: enabled LLM layer never invents authoritative identifiers

Given an LLM-enabled configuration and a chunk whose deterministic
metadata carries `requirementId="REQ-123"`
When the LLM layer runs
Then the resulting `ContextualChunk.metadata.requirementId` is
unchanged (`"REQ-123"`)
And the LLM-suggested entities appear under
`metadata.pi_assumption.entities`
And the `pi_assumption` block is recorded as
`KnowledgeState.ASSUMPTION`.

### Requirement: ContextualChunk round-trip

The `ContextualChunk` produced by the enricher MUST round-trip
through the deterministic JSON serializer so two equivalent enricher
runs produce byte-identical canonical files. The Phase 1 round-trip
test `tests/test_canonical_roundtrip.py` MUST continue to pass
after Phase 2 introduces the enricher.

#### Scenario: equivalent enricher runs are byte-identical

Given two enricher runs over the same chunk, document and source
When both `ContextualChunk` instances are serialised to canonical
JSON
Then the two serialised files are byte-identical
And the parsed-back instances are structurally equal.

## Phase 2 task coverage

The change lists Phase 2 task 55 (three-layer context enrichment
producing `ContextualChunk` records) and the `context-enrichment`
slice of task 58 (Phase 2 spec scenarios) and task 59 (focused
regression tests per enricher).

Out of scope:

- the `LocalLLMPort` binding — the Phase 5 capability
  `small-local-llm-port` is the implementation site; this Phase 2
  spec only documents the contract the LLM layer must respect;
- the embedding model that consumes the `ContextualChunk` (Phase 4
  task 70);
- the reranker that consumes the `ContextualChunk` (Phase 4 task
  74).
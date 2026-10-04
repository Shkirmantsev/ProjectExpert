# Portable Version-Aware Project Intelligence Platform
## Architecture Foundation v0.8

> Status: architect-reviewed consolidated architecture baseline  
> Goal: a portable, local-first, Git-versioned project intelligence layer for humans and AI coding agents.

---

## 1. Purpose

Design a **portable, local-first, version-aware Project Intelligence Platform** that can be attached to an arbitrary software repository and provide a shared project knowledge, retrieval and context layer for:

- developers;
- software architects;
- project managers;
- analysts;
- AI coding agents such as Claude Code, Codex, OpenCode, Hermes and future compatible agents.

The platform shall act as the **local semantic, architectural and business memory of the software project**.

The platform must be:

- agent-neutral;
- model-neutral;
- storage-neutral at the architectural level;
- offline-capable;
- suitable for restricted enterprise environments;
- version-aware;
- reproducible;
- inspectable;
- portable;
- easy to install and run;
- commercially usable and redistributable with a dependency stack whose licenses permit the intended usage;
- preferably deployable as one container;
- optionally deployable as two containers when model-runtime isolation is useful.

---

# 1. Core Architectural Model

```text
Git-versioned canonical knowledge
        ↕
Import / Hydrate  ↔  Export / Materialize
        ↕
Runtime Working Knowledge Store
        ↓
Retrieval + Context Engine
        ↓
Humans / Local AI / External Coding Agents
```

The central principle is:

```text
Git
    = durable, versioned project knowledge

Markdown / YAML / JSONL shards
    = canonical portable serialization

Runtime DB
    = optimized working knowledge state

Embedding Model
    = semantic indexing/search mechanism

Knowledge Graph
    = explicit project relationships

Small Local LLM
    = cheap local intelligence

Query Orchestrator
    = routing and control plane

Context Assembler
    = deterministic bounded-context builder

Strong external agent
    = deep reasoning, architecture and implementation

MCP
    = agent-to-tools/context interface

A2A
    = agent-to-agent interoperability interface

REST
    = generic application integration interface

CLI / Web UI
    = human-facing interfaces

OpenSpec
    = intent/specification/change-management layer
```

---

# 2. Sources of Truth

The platform shall distinguish between different classes of project information.

## 3.1 OpenSpec
Normative development intent and expected behaviour.

## 3.2 Source Code and Tests
Implementation evidence.

## 3.3 LLM Wiki
Structured, human-readable explanation of project knowledge.

## 3.4 ADRs
Architecture decisions and rationale.

## 3.5 Git History
Historical and version-evolution evidence.

## 3.6 External Documentation
Business, protocol and requirements evidence with explicit provenance.

Generated Wiki information must never silently override normative specifications or verified source evidence.

---

# 3. Supported Knowledge Sources

The platform shall ingest and understand:

- application source code;
- tests;
- Maven and Gradle project structures;
- external JAR dependencies;
- source JARs where available;
- bytecode and public library APIs;
- OpenSpec specifications;
- OpenSpec changes;
- ADRs;
- requirements;
- Pflichtenheft documents;
- Markdown;
- HTML;
- PDF;
- supported office documents;
- local external-documentation directories;
- `tmp/local/source/**`;
- optionally Confluence;
- optionally internal websites and intranet applications;
- other sources through pluggable adapters.

---

# 4. License and Dependency Governance

The platform is intended to be usable by private individuals and companies, including large enterprises, and should remain suitable for redistribution or commercial sale.

Therefore every bundled library, framework, model runtime, parser, database component and other third-party dependency must have its license explicitly tracked.

## 5.1 Preferred License Policy

Prefer permissive OSI-approved licenses that normally allow commercial use, modification and redistribution, subject to their notice/attribution conditions.

Preferred examples include:

```text
Apache-2.0
MIT
BSD-2-Clause
BSD-3-Clause
ISC
```

Apache-2.0 is preferred where practical because it is permissive and contains an explicit patent grant.

## 5.2 Review-required Licenses

Licenses with reciprocal, file-level copyleft, linking conditions or other distribution obligations must not be introduced automatically.

Examples that require explicit legal/architecture review may include:

```text
MPL-2.0
EPL-2.0
LGPL-family licenses
GPL-family licenses
AGPL-family licenses
```

This does **not** mean that all such licenses are unusable. It means they must be evaluated against the intended distribution model.

## 5.3 Restricted / Non-commercial / Source-available Licenses

Components whose terms prohibit or materially restrict:

- commercial use;
- redistribution;
- SaaS use;
- modification;
- use by companies;
- resale;

must not be part of the default dependency stack unless explicitly approved.

This includes licenses containing terms such as:

```text
Non-Commercial
Research Only
Source Available with commercial restriction
Field-of-use restriction
```

## 5.4 Model Licenses Are Separate

The license of:

- model weights;
- tokenizer;
- training artifacts;
- inference runtime;
- embedding model;
- reranker;

must be evaluated separately.

A Python/Java library may be Apache-2.0 while the model weights it downloads use a different license.

## 5.5 Automated License Gate

The build should generate and validate:

- dependency inventory;
- SPDX identifiers;
- SBOM;
- bundled model licenses;
- NOTICE obligations.

Conceptually:

```text
dependency discovered
        ↓
license identified
        ↓
allowlist / review-list / deny-list
        ↓
CI license gate
```

No new dependency should enter a release without a known license.

The same rule applies to dynamically installed plugins, hook packages, UI extensions and agent adapters. A plugin must not be enabled until its license identity and compatibility policy are known.

---

# 5. Git as the Versioning Backbone

Git is the primary versioning mechanism for durable project knowledge.

The Git repository may contain:

- LLM Wiki pages;
- normalized documentation snapshots;
- knowledge manifests;
- provenance information;
- knowledge-graph entities;
- knowledge-graph relationships;
- OpenSpec traceability;
- architecture metadata;
- source metadata;
- deterministic enrichment metadata.

Binary runtime databases, vector indexes, ANN indexes and search-engine internal files should normally **not** be committed.

---

# 6. Canonical Knowledge vs Runtime Working Knowledge

The platform explicitly separates two representations.

## 7.1 Canonical Git-Portable Knowledge

Portable, Git-versioned and human-inspectable.

Example:

```text
project-knowledge/
├── wiki/
├── graph/
├── chunks/
├── sources/
├── objects/
├── manifests/
└── project-context.yaml
```

The representation must remain understandable without the runtime database.

## 7.2 Runtime Working Knowledge Store

Optimized operational state.

It may contain:

- normalized entities;
- relations;
- chunks;
- metadata;
- full-text indexes;
- sparse indexes;
- dense vectors;
- ANN indexes;
- graph indexes;
- cache state;
- source mappings;
- working-tree overlay.

The runtime DB is **not merely a one-time generated cache**.

It is the active working knowledge representation used while the project is running.

The essential requirement is bidirectional synchronization:

```text
Git Portable Knowledge
        ↓ import / hydrate
Runtime Working Knowledge
        ↑ export / materialize
Git Portable Knowledge
```

---

# 7. Bidirectional DB ↔ Git Knowledge Lifecycle

This is a fundamental invariant.

## 8.1 Restore / Hydrate

After checkout, clone, pull or branch switch:

```text
Git branch / commit
        ↓
read manifests
        ↓
load canonical shards
        ↓
restore runtime DB
        ↓
restore graph/search state
        ↓
reuse cached embeddings where hashes match
```

## 8.2 Enrich Runtime Knowledge

The running system can then ingest:

- changed source code;
- new local files;
- `tmp/local/source/**`;
- JARs;
- requirements;
- external documentation;
- OpenSpec changes;
- configured web/Confluence sources.

It parses, chunks, contextualizes, extracts graph relations and vectorizes only new/changed information.

## 8.3 Materialize Back to Git

When durable knowledge has changed:

```text
Runtime Working Knowledge
        ↓
normalize
        ↓
deterministic serialization
        ↓
shard
        ↓
update manifests
        ↓
write Git Portable Knowledge
        ↓
git diff
        ↓
validation
        ↓
commit
```

Therefore the portable files are not merely input files. They are the **canonical serialization format of durable runtime knowledge**.

## 8.4 Round-trip Requirement

The following round trip must preserve equivalent durable knowledge:

```text
Portable Knowledge A
        ↓ hydrate
Runtime DB
        ↓ materialize
Portable Knowledge B
```

`A` and `B` may differ in harmless formatting/order details only if canonical serialization normalizes them deterministically.

The recommended implementation is deterministic enough that unchanged knowledge produces no Git diff.

---

# 8. Local Dynamic Source Inbox

Add the project-local directory:

```text
tmp/local/source/
```

It acts as a dynamic ingestion inbox.

It may contain arbitrary nested subdirectories:

```text
tmp/local/source/
├── requirements/
├── customer/
├── protocols/
├── confluence-export/
├── diagrams/
├── jar-docs/
└── arbitrary/subdirectories/...
```

Supported parsers recursively discover files.

## 9.1 Default Git Behaviour

`tmp/local/**` should normally be excluded from Git.

Example:

```gitignore
tmp/local/**
```

The directory is intended for:

- temporary customer files;
- local-only requirements;
- confidential material;
- experiment inputs;
- documents that should enrich knowledge without being committed.

## 9.2 Source Promotion Policy

A local source can use one of three policies:

```text
LOCAL_ONLY
    Parse/index locally; never commit source or canonical snapshot.

REFERENCE
    Persist only provenance/reference metadata.

SNAPSHOT
    Normalize/copy an approved representation into canonical Git knowledge.
```

This distinction is important for confidential enterprise documents.

## 9.3 Recursive Incremental Ingestion

The engine watches or scans the folder recursively and uses content hashes.

```text
new / changed file
       ↓
parser selection
       ↓
content hash
       ↓
parse / chunk / contextualize
       ↓
metadata + graph + vectors
       ↓
runtime DB
       ↓
optional durable materialization
```

Deleted files must also invalidate or mark derived knowledge as stale according to provenance.

---

# 9. Git Scalability and Large-File Strategy

A single large JSON, JSONL, graph dump or index file must **not** become the canonical Git representation.

Large monolithic files cause:

- expensive clone/checkout;
- poor diffs;
- merge conflicts;
- repository growth;
- hosting-provider limits;
- whole-file rewrites;
- expensive branch switching;
- high parser memory usage.

Canonical project knowledge shall therefore be **sharded**.

## 10.1 Sharded Graph Storage

Prefer structures such as:

```text
graph/
├── nodes/
│   ├── requirements/
│   ├── java-classes/
│   ├── components/
│   ├── specs/
│   └── dependencies/
└── edges/
    ├── implements/
    ├── depends-on/
    ├── calls/
    ├── tested-by/
    └── references/
```

or hash-prefix shards:

```text
graph/nodes/00/
graph/nodes/01/
...
graph/nodes/ff/
```

## 10.2 Content-Addressed Objects

Stable generated objects may be stored by hash:

```text
objects/
├── 00/
│   └── 00ab...json
├── 01/
│   └── 01f2...json
└── ...
```

A manifest maps logical entities to content objects.

Advantages:

- unchanged objects are not rewritten;
- identical content can be reused between branches;
- Git deduplication is improved;
- runtime hydration skips unchanged content;
- cache identity aligns with content identity.

## 10.3 Manifests

Each knowledge family has a compact manifest describing:

- shard IDs;
- paths;
- content hashes;
- source hashes;
- schema version;
- entity counts;
- dependencies between shards.

Runtime hydration operates from these manifests.

## 10.4 Git LFS

Git LFS may optionally be used for genuinely large binary source artifacts such as:

- PDF packages;
- binary requirement documents;
- archived exports.

Git LFS should not be required for the structured canonical knowledge model.

---


# 10. Open Knowledge Format (OKF) Compatibility Profile

The human-readable Wiki layer should support the **Open Knowledge Format (OKF)** as its preferred portable knowledge profile.

OKF is a file format/convention, not the runtime transport protocol of this platform. MCP, A2A and REST remain runtime protocols/interfaces.

The platform should target a configurable OKF version and initially support **OKF v0.2**.

## 0.1 OKF Bundle Boundary

The Git-versioned Wiki should be a valid or intentionally profiled OKF bundle:

```text
project-knowledge/
└── wiki/
    ├── index.md
    ├── log.md
    ├── architecture/
    │   ├── index.md
    │   └── ...
    ├── business/
    ├── components/
    ├── dependencies/
    ├── requirements/
    └── specifications/
```

The bundle-root `index.md` should declare the targeted OKF version:

```yaml
---
okf_version: "0.2"
---
```

Every non-reserved concept Markdown file should contain parseable YAML frontmatter and a non-empty `type`.

Example:

```yaml
---
type: Component
title: Packing Service
description: Handles the packing-machine integration and packing lifecycle.
resource: "project://component/packing-service"
tags:
  - packing
  - integration
pi_status: verified
pi_source_hash: "..."
pi_project_version: "..."
---
```

Platform-specific extension fields should use a stable project-specific prefix such as `pi_` so that OKF readers can ignore unknown metadata while the Project Intelligence Platform can retain richer provenance and lifecycle data.

## 0.2 Reserved Files

The implementation must preserve OKF reserved semantics for:

```text
index.md
log.md
```

`index.md` is used for progressive disclosure and navigation.

`log.md` records chronological updates for the corresponding scope.

## 0.3 OKF and Internal Runtime Data

The following are **not** part of the OKF Wiki contract:

- dense vectors;
- ANN indexes;
- sparse index internals;
- runtime database pages;
- temporary task context;
- model caches.

These remain derived runtime state.

Graph entities, provenance and technical manifests may remain separate canonical structures while referencing the corresponding OKF concepts.

## 0.4 OKF Validation

The materialization pipeline should run deterministic OKF validation before a durable commit.

Validation should check at minimum:

- parseable YAML frontmatter;
- mandatory `type`;
- valid reserved filenames;
- root declared OKF version when configured;
- stable links where possible;
- platform provenance extensions;
- no accidental runtime/binary files inside the OKF bundle.

The CI/release pipeline should include an OKF conformance gate.

## 0.5 Forward Compatibility

The core domain model must not be coupled to a specific OKF minor version.

An `OkfAdapter` should translate between:

```text
Internal Knowledge Model
        ↕
OKF profile/version
```

This allows later OKF revisions to be supported without redesigning the runtime knowledge model.

---

# 11. Version Identity

Runtime project state is identified approximately by:

```text
repository identity
+
Git HEAD commit
+
working-tree fingerprint
+
knowledge schema version
+
embedding model version
+
index schema version
```

Branch names are mutable pointers and must not be treated as immutable version IDs.

---

# 12. Git Branches, Tags and Working Trees

The platform shall support:

- branch switching;
- release branches;
- tags;
- historical commits;
- Git worktrees;
- uncommitted changes.

Uncommitted changes form a temporary overlay:

```text
HEAD knowledge
      +
working-tree overlay
      =
effective runtime context
```

A branch switch triggers reconciliation, not necessarily full rebuild.

---

# 13. Content-Addressed Processing

Expensive derived information is associated with content hashes.

```text
source content
      ↓
SHA-256
      ↓
parsed structure
      ↓
contextualized chunks
      ↓
embedding/cache
```

Identical content on multiple branches should reuse:

- parsed structures;
- chunks;
- contextualized chunks;
- embeddings;
- deterministic summaries;
- entity extraction results where safe.

---

# 14. Structured Code Intelligence

Source-code understanding shall not rely only on text chunking.

For Java the platform should understand:

- Maven modules;
- packages;
- classes;
- interfaces;
- implementations;
- methods;
- constructors;
- inheritance;
- annotations;
- calls;
- dependencies;
- configuration;
- JPA mappings;
- tests;
- API boundaries.

Possible sources include:

- Java AST/parser libraries;
- compiler metadata;
- Maven/Gradle metadata;
- JAR inspection;
- source JARs;
- bytecode;
- `jar`;
- `javap`;
- `jdeps`;
- equivalent programmatic libraries.

The container may bundle the Java tooling required for these operations, subject to the project license policy.

---

# 15. JAR and Dependency Intelligence

JARs are first-class knowledge sources.

The platform should extract:

- artifact coordinates;
- versions;
- packages;
- classes;
- interfaces;
- signatures;
- annotations;
- inherited types;
- modules;
- resources;
- source JAR content;
- public APIs;
- dependency relationships.

Relevant external dependencies become Wiki/graph entities rather than opaque binaries.

---

# 16. Canonical Knowledge Graph

Example entity types:

- Requirement;
- Specification;
- OpenSpecChange;
- ADR;
- BusinessConcept;
- Component;
- Module;
- JavaClass;
- JavaMethod;
- Interface;
- API;
- Dependency;
- DatabaseTable;
- Protocol;
- Test;
- DocumentationSource;
- Document;
- Section;
- Chunk.

Example relations:

```text
IMPLEMENTS
SATISFIES
DEPENDS_ON
CALLS
USES
IMPLEMENTED_BY
DEFINED_BY
PART_OF
DOCUMENTED_BY
TESTED_BY
REFERENCES
SUPERSEDES
DESCRIBES
```

The canonical graph is Git-friendly and sharded.

The runtime graph index is derived.

---

# 17. ANN Graphs vs Knowledge Graphs

These concepts must remain separate.

## ANN Graph
Example: HNSW.

Purpose: efficient nearest-neighbour search in vector space.

## Knowledge Graph
Purpose: explicit architectural/business/software relationships.

ANN topology is not project semantics.

---

# 18. Ingestion Pipeline

```text
Git / Code / Docs / JARs / OpenSpec / tmp/local/source
                    │
                    ↓
               Source Parsing
                    │
           ┌────────┴────────┐
           ↓                 ↓
    structural data        raw text
           │                 │
           └────────┬────────┘
                    ↓
          Semantic / Structural
                 Chunking
                    ↓
            Context Enrichment
                    ↓
             Canonical Chunks
                    ↓
      ┌─────────────┼────────────────┐
      ↓             ↓                ↓
Dense Embedding  Sparse/BM25     Metadata
      │             │                │
      └─────────────┼────────────────┘
                    │
                    ├────────→ Knowledge Graph
                    │
                    ↓
             Runtime Working DB
```

---

# 19. Semantic and Structural Chunking

Avoid naive fixed-size chunking where structure exists.

Prefer boundaries such as:

- document section;
- heading;
- Java class;
- Java method;
- OpenSpec element;
- requirement;
- protocol message;
- table;
- architecture unit.

Chunks retain parent links.

---

# 20. Hierarchical Knowledge

```text
Document
│
├── Chapter
│   ├── Section
│   │   ├── Chunk
│   │   └── Chunk
│   └── Section
```

Searchable representations may exist for:

```text
document summary
section summary
chunk
```

Retrieval can reattach parent and adjacent context.

---

# 21. Chunk Model

```text
Chunk
├── id
├── rawText
├── contextualText
├── metadata
├── parentId
├── childIds
├── entityIds
├── sourceReference
├── contentHash
└── provenance
```

---

# 22. Context Enrichment

Three layers:

## 22.1 Deterministic
Examples:

- file;
- title;
- heading hierarchy;
- page;
- section;
- package;
- class;
- method;
- Git revision;
- requirement ID;
- OpenSpec ID;
- version;
- language;
- validity dates.

## 22.2 Domain Rules / Ontology

Example:

```text
path psb/packing/**
→ businessDomain = PACKING
→ system = PSB
```

## 22.3 Optional Small Local LLM

Allowed tasks:

- concise semantic context;
- summaries;
- candidate entities;
- candidate relations.

It must not invent authoritative identifiers, versions, dates or security levels.

---

# 23. Metadata as Correctness Constraints

Metadata supports deterministic filtering and auditing.

Examples:

```text
documentId
version
language
section
businessDomain
module
className
requirementId
validFrom
validTo
Git commit
source path
page
line
security classification
content hash
```

Rule:

```text
semantic meaning
    → contextualized text

exact / filterable / auditable facts
    → metadata
```

---

# 24. Temporal and Version-Aware Retrieval

Correctness constraints such as date and release are applied through metadata.

```text
validFrom <= queryDate
AND
(validTo IS NULL OR validTo >= queryDate)
```

Thus:

```text
vector similarity
    = semantic relevance

metadata
    = correctness boundaries
```

---

# 25. Embedding Model

The embedding model:

```text
text/code representation
      ↓
embedding
      ↓
vector
```

It does not directly control the vector database and it is not a reasoning engine.

The application layer invokes it.

Requirements:

- local execution;
- multilingual retrieval;
- German;
- English;
- Ukrainian;
- optionally Russian;
- code retrieval;
- CPU-capable deployment;
- replaceable provider;
- commercially usable license for the selected model/runtime.

---

# 26. Sparse and Exact Retrieval

Dense vectors are insufficient for engineering identifiers.

The system must reliably find:

```text
GEN_3.0.03
ILO-5193
RpaVaryToteJpaMapper
PSB_FINISH_PACK
0x84721
```

Therefore support:

- BM25 or equivalent;
- exact identifier lookup;
- symbol lookup;
- metadata lookup.

---

# 27. Hybrid Retrieval

Default retrieval:

```text
query
  │
  ├──────────────┐
  ↓              ↓
Dense ANN     Sparse/BM25
  │              │
  └──────┬───────┘
         ↓
       Fusion
```

Pure-vector search is not the default.

---

# 28. ANN Candidate Generation

Supported approaches may include:

- flat/exact search;
- HNSW;
- IVF;
- future ANN techniques.

ANN is an implementation choice based on:

- index size;
- latency;
- memory;
- recall requirements.

---

# 29. Multi-Stage Retrieval

```text
large corpus
    ↓
cheap candidate generation
    ↓
dense + sparse fusion
    ↓
metadata/version/security constraints
    ↓
graph expansion
    ↓
hierarchy expansion
    ↓
reranking
    ↓
small high-quality result set
    ↓
Context Assembler
```

Principle:

```text
retrieval = high recall
reranking = high precision
```

---

# 30. Optional Advanced Reranking

Pluggable advanced mechanisms may include:

- cross-encoders;
- multi-vector retrieval;
- ColBERT-style late interaction;
- stronger rerankers.

Use them only on bounded candidate sets.

---

# 31. Graph Expansion

Example:

```text
Chunk 7.4.2
      │
      └─ DESCRIBES → FinishPack
                         │
                         ├─ PART_OF → PackingProtocol
                         ├─ IMPLEMENTED_BY → PackingService
                         ├─ DEFINED_BY → GEN_3.0.03
                         └─ TESTED_BY → FinishPackIT
```

Graph expansion enriches semantic hits with project relationships.

---

# 32. Context Assembler

The Context Assembler is a first-class component.

It combines:

- chunks;
- parent sections;
- code symbols;
- requirements;
- OpenSpec;
- ADRs;
- graph neighbours;
- versions;
- sources;
- provenance;
- confidence.

It must:

- deduplicate;
- enforce context budget;
- preserve citations;
- prefer authoritative evidence;
- detect conflicts;
- expose uncertainty.

The external LLM should not need to scan the whole repository to reconstruct context.

---

# 33. Retrieval-First Agent Access Strategy

The default principle is:

> Use the cheapest deterministic retrieval mechanism first and escalate only when needed.

For an agent request:

```text
1. exact symbol / metadata lookup
2. sparse search
3. dense semantic search
4. hybrid fusion
5. graph + hierarchy expansion
6. reranking
7. bounded Context Assembly
8. strong LLM reasoning only over the selected context
9. direct source-file scan only if retrieval evidence is insufficient
```

This is intended to minimize:

- LLM token consumption;
- latency;
- repeated repository scanning;
- unnecessary file reads;
- external model cost.

MCP tools should expose these high-level retrieval capabilities directly.

---

# 34. Query Orchestrator

The deterministic Query Orchestrator chooses between:

## Level 0 — Direct Retrieval

Example:

```text
Where is OrderStatus declared?
```

## Level 1 — Retrieval + Small Local LLM

Example:

```text
Explain the FinishPack protocol message.
```

## Level 2 — Strong External Agent

Example:

```text
Implement REQ-471 and adapt integration tests.
```

Delegation policy belongs to the orchestrator, not to the small model.

---

# 35. Small Local LLM

An optional compact local LLM may perform:

- query classification;
- query rewriting;
- contextualization;
- entity extraction;
- relation extraction;
- short summarization;
- lightweight reranking;
- context compression;
- simple Q&A.

Target properties:

- CPU-first;
- commodity hardware;
- preferably approximately 1 GB or less dedicated GPU memory if GPU is used;
- GPU optional;
- commercially compatible model/runtime license.

It is not the main coding/architecture model.

---

# 36. MCP Integration

MCP is the primary interface by which coding agents access project tools and context.

Potential semantic MCP tools:

```text
project.search
project.retrieve_context
project.get_entity
project.get_component
project.get_requirement
project.get_spec
project.get_architecture
project.get_dependency
project.find_implementation
project.trace_requirement
project.find_references
project.get_project_version
project.get_conflicts
project.get_stale_knowledge
project.build_task_context
project.materialize_knowledge
project.refresh_sources
```

Agents should not need to know whether results came from:

- BM25;
- vector ANN;
- graph traversal;
- AST;
- Wiki;
- metadata;
- exact symbol indexes.

---


# 37. Versioned Agent Skill Distributed with the MCP Server

The Project Intelligence Platform shall ship a **canonical versioned Agent Skill** that teaches compatible agents how to use its MCP server efficiently and safely.

The skill is not optional documentation. It is part of the public integration contract.

The skill must follow the Agent Skills open format and use a valid `SKILL.md` with:

- `name`;
- `description`;
- `license`;
- optional `compatibility`;
- version and protocol metadata;
- supporting `references/`, `scripts/` and `assets/` only where useful.

## 0.1 Canonical Skill Package

Recommended structure:

```text
distribution/
└── skills/
    └── project-intelligence/
        ├── SKILL.md
        ├── references/
        │   ├── MCP-TOOLS.md
        │   ├── RETRIEVAL-POLICY.md
        │   ├── VERSIONING.md
        │   ├── OKF-PROFILE.md
        │   └── SECURITY.md
        ├── scripts/
        │   └── doctor.*
        └── assets/
            └── config-examples/
```

The primary `SKILL.md` should remain concise and rely on progressive disclosure.

Detailed MCP tool descriptions, examples and compatibility data belong in referenced files rather than bloating the base skill.

## 0.2 Skill Metadata Contract

Example:

```yaml
---
name: project-intelligence
description: Use the Project Intelligence MCP server to retrieve version-correct project context, trace requirements, inspect architecture and dependencies, build bounded task context, and refresh or materialize approved project knowledge. Use before scanning the repository directly when project context is needed.
license: Apache-2.0
compatibility: Requires access to a compatible Project Intelligence MCP server. Designed for Agent-Skills-compatible coding agents; vendor adapters may add installation metadata.
metadata:
  author: "project-intelligence"
  version: "1.4.0"
  mcp-api: ">=1.3.0 <2.0.0"
  knowledge-schema: ">=0.7.0 <1.0.0"
  okf-profile: "0.2"
  distribution-schema: "1"
---
```

All custom metadata values should remain strings for Agent Skills portability.

`allowed-tools` may be supported when useful, but the architecture must not depend on it because support can vary by client.

## 0.3 Skill Behaviour

The skill shall explicitly teach agents the desired cost-efficient access policy:

```text
1. Inspect project/version capabilities.
2. Prefer project MCP retrieval over broad repository scanning.
3. Use exact/symbol search when identifiers are known.
4. Use hybrid retrieve_context for semantic questions.
5. Follow requirement/spec/graph links instead of opening unrelated files.
6. Request bounded TaskContext for implementation tasks.
7. Open raw source only for selected evidence or when retrieval is insufficient.
8. Preserve version/security filters.
9. Cite provenance returned by the server.
10. Materialize durable knowledge only through explicit approved workflow.
```

The skill must also define:

- when not to use a tool;
- how to react to stale or conflicting knowledge;
- how to handle incompatible server/skill versions;
- how to avoid bypassing project security policy;
- how to distinguish read-only retrieval from write/materialization actions.

---

# 38. Skill Distribution Plane

The MCP server should be able to act as the canonical distribution source for the current skill package.

Conceptually:

```text
MCP Server
├── tools
├── resources
├── prompts (optional)
└── skill distribution resources
```

Recommended custom resources:

```text
project-intelligence://distribution/manifest
project-intelligence://skills/index
project-intelligence://skills/project-intelligence/<version>/SKILL.md
project-intelligence://skills/project-intelligence/<version>/references/...
project-intelligence://skills/project-intelligence/<version>/assets/...
```

The exact URI namespace is implementation-defined, but it must be stable and versioned.

## 0.1 Distribution Manifest

The server should expose a machine-readable distribution manifest similar to:

```yaml
platformVersion: "0.7.0"
mcpApiVersion: "1.3.0"
knowledgeSchemaVersion: "0.7.0"
distributionSchemaVersion: "1"
skill:
  name: project-intelligence
  version: "1.4.0"
  sha256: "..."
  mcpApiRange: ">=1.3.0 <2.0.0"
okf:
  supported:
    - "0.2"
agentAdapters:
  codex: "1.0.0"
  claude-code: "1.0.0"
  opencode: "1.0.0"
```

## 0.2 Snapshot vs Runtime Distribution

Not every agent loads skills dynamically from MCP at runtime.

Therefore the architecture must support both:

```text
A. Runtime discovery
   client reads skill/resources from MCP

B. Build/install-time snapshot
   plugin/installer packages a snapshot of the canonical skill
```

The canonical skill content remains single-source even when individual agent ecosystems require snapshots.

## 0.3 Integrity

Every distributable skill/plugin package should carry:

- semantic version;
- content hash;
- license;
- build provenance;
- compatible MCP API range.

Release artifacts should optionally be signed.

---

# 39. Protocol and Artifact Version Compatibility

Versioning must be explicit across independently evolving parts.

Track at least:

```text
platformVersion
mcpApiVersion
a2aAdapterVersion
knowledgeSchemaVersion
okfProfileVersion
skillVersion
pluginDistributionSchemaVersion
agentAdapterVersion
runtimeIndexSchemaVersion
```

## 0.1 Compatibility Handshake

At connection/startup:

```text
Agent Adapter / Skill
        ↓
read server capabilities
        ↓
compare supported version ranges
        ↓
compatible?
   ├── yes → continue
   └── no  → fail clearly / offer upgrade instructions
```

The server should expose capability information without requiring an LLM.

## 0.2 Semantic Versioning

Public API/skill/plugin contracts should use semantic versioning where practical.

Breaking MCP tool schema changes require a major compatibility boundary or explicit compatibility adapter.

Skill releases should declare which MCP API versions they understand.

A newer server may retain compatibility adapters for older released skills for a bounded support window.

---

# 40. Agent Integration Packaging Layer

The project shall provide first-class installable integration packages for major coding-agent ecosystems where a supported extension/plugin mechanism exists.

The core platform remains vendor-neutral.

Use a Ports-and-Adapters boundary:

```text
                    Project Intelligence Core
                              │
                     Agent Integration Port
                              │
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
     Codex Adapter      Claude Code Adapter    OpenCode Adapter
        │                     │                     │
     plugin pkg           plugin pkg            npm/local plugin
        │                     │                     │
       MCP + skill          MCP + skill           MCP + instructions/skill
```

Vendor-specific configuration must not leak into the retrieval/domain core.

---

# 41. Codex / ChatGPT Plugin Distribution Profile

The distribution pipeline should generate a portable OpenAI Agent Plugin package containing the canonical skill and MCP configuration.

Conceptually:

```text
dist/codex/
├── plugin.json
├── mcp.json
├── skills/
│   └── project-intelligence/
│       ├── SKILL.md
│       └── ...
├── assets/
└── optional OpenAI-specific extension metadata
```

A compatibility fallback for environments that still require `.codex-plugin/plugin.json` may also be generated.

Important behaviour:

- the skill remains generated from the canonical skill source;
- MCP configuration points to the local or remote Project Intelligence MCP endpoint;
- skill/MCP compatibility metadata is validated during packaging;
- OpenAI-specific metadata remains outside the core domain model;
- if a platform imports a skill from MCP as a snapshot, a new plugin release/rescan is required after the canonical skill changes.

---

# 42. Claude Code Plugin Distribution Profile

The project should generate a Claude Code plugin package from the same canonical integration sources.

Conceptually:

```text
dist/claude-code/
├── .claude-plugin/
│   └── plugin.json
├── .mcp.json
├── skills/
│   └── project-intelligence/
│       ├── SKILL.md
│       └── ...
├── commands/        # optional
├── agents/          # optional
└── README.md
```

The Claude Code adapter should:

- register/connect the MCP server;
- expose the same canonical Agent Skill;
- optionally provide a minimal command/bootstrap experience;
- avoid duplicating business/retrieval logic in plugin scripts;
- be marketplace-ready when distribution through a marketplace is desired.

The plugin slug should be treated as stable after public release.

---

# 43. OpenCode Plugin Distribution Profile

OpenCode supports both MCP server configuration and JavaScript/TypeScript plugins.

The project should therefore provide an OpenCode integration package that can:

- register or simplify configuration of the Project Intelligence MCP server;
- provide project-specific integration hooks only where they add value;
- expose/install the canonical Agent Skill when the active OpenCode version supports the relevant skill convention;
- otherwise inject only the minimal instructions/bootstrap required to make MCP use reliable.

Conceptually:

```text
dist/opencode/
├── package.json
├── plugin/
│   └── project-intelligence.ts
├── skill/
│   └── project-intelligence/
│       └── SKILL.md
├── config/
│   └── opencode.example.jsonc
└── README.md
```

The plugin should be publishable as a versioned npm package or usable as a local project plugin.

Again, the plugin is an adapter; all actual knowledge/retrieval logic remains in the Project Intelligence core.

---

# 44. Generic Agent Integration Profile

For coding agents without a dedicated plugin package, provide a generic bundle:

```text
dist/generic-agent/
├── skills/
│   └── project-intelligence/
├── mcp/
│   ├── stdio-example.json
│   └── http-example.json
├── AGENTS.example.md
└── README.md
```

This profile should maximize compatibility through:

- standard MCP;
- Agent Skills;
- optional A2A;
- plain Markdown instructions.

Additional agent-specific adapters such as IDE/coding-assistant integrations can be added without changing the core.

---

# 45. Plugin Generation Pipeline

Vendor packages should be generated rather than maintained as independent hand-written copies.

```text
Canonical Sources
├── Agent Skill
├── MCP endpoint metadata
├── capability manifest
├── license metadata
└── integration templates
        ↓
Plugin Packager
        ↓
┌──────────────┬──────────────────┬────────────────┐
│ Codex bundle │ Claude Code      │ OpenCode       │
│              │ bundle           │ package        │
└──────────────┴──────────────────┴────────────────┘
```

The build must fail if generated packages disagree on:

- skill content hash;
- skill version;
- MCP API compatibility range;
- license;
- server identity;
- required capabilities.

---

# 46. Agent Adapter Contract

Every agent-specific adapter should implement a narrow contract conceptually equivalent to:

```text
AgentIntegrationAdapter
├── detect()
├── install()
├── configureMcp()
├── installSkill()
├── verifyCompatibility()
├── healthCheck()
├── uninstall()
└── describe()
```

This contract supports one-click setup while keeping installers replaceable.

Adapters must not own retrieval/business rules.

---

# 47. Capability Discovery

The MCP/API layer should expose deterministic capability discovery.

Example logical response:

```json
{
  "serverVersion": "0.7.0",
  "mcpApiVersion": "1.3.0",
  "knowledgeSchemaVersion": "0.7.0",
  "features": {
    "hybridRetrieval": true,
    "graphExpansion": true,
    "okf": ["0.2"],
    "materialization": true,
    "a2a": true,
    "localLlm": false
  }
}
```

The skill and plugins must query or receive these capabilities rather than assuming every deployment exposes every optional feature.

---

# 48. Security and Trust for Skills and Plugins

Skills and plugins are executable/instruction-bearing supply-chain artifacts and must be treated accordingly.

Release controls should include:

- pinned version;
- content hash;
- SBOM where applicable;
- dependency/license scan;
- malware/secret scan;
- deterministic build where practical;
- signature support;
- source repository/provenance metadata;
- clear permissions;
- explicit network requirements;
- no hidden auto-install of unrelated software.

A plugin must never silently weaken the core platform's security policy.

Write/materialization tools remain approval-controlled even when a skill or plugin requests them.

---

# 49. Integration Quality Gates and Evals

The project needs repeatable regression tests for agent integration, not only unit tests for the MCP server.

Minimum evaluation suites:

```text
Skill activation tests
MCP tool-selection tests
retrieval-first compliance tests
version-mismatch tests
stale/conflict handling tests
security-filter tests
plugin install/uninstall smoke tests
OKF materialization/conformance tests
round-trip DB ↔ Git tests
branch-switch tests
token/context-cost tests
```

Representative agent scenarios should verify that an integrated coding agent:

1. calls MCP retrieval before broad file scanning for project-context questions;
2. uses exact lookup for known identifiers;
3. respects Git/project version filters;
4. requests bounded context for implementation work;
5. opens only selected raw files when necessary;
6. reports provenance/conflicts;
7. avoids materialization without approval.

Metrics should include:

- retrieval recall/precision;
- reranker quality;
- context size;
- external LLM token consumption;
- latency;
- cache reuse;
- branch-switch hydration time;
- stale-knowledge detection;
- plugin setup success rate.

---

# 50. A2A Integration

If the platform contains an orchestrator/local-agent capability, it should be able to participate in **Agent2Agent (A2A)** communication through a pluggable A2A adapter.

The architecture should support both directions:

```text
External Agent
      │
      │ A2A
      ↓
Project Intelligence Agent
```

and:

```text
Project Intelligence Agent
      │
      │ A2A
      ↓
External Agent
```

A2A is used for **agent-to-agent task collaboration**.

MCP remains the primary mechanism for **tools, context and project operations**.

These interfaces are complementary, not substitutes.

The implementation should track a stable released A2A specification through an adapter so protocol evolution does not leak into the core domain model.

---

# 51. External Coding Agents

Supported integration targets may include:

- Claude Code;
- Codex;
- OpenCode;
- Hermes;
- A2A-compatible agents;
- future enterprise agents.

Primary usage:

```text
Coding Agent
     │
     │ MCP
     ↓
Project Intelligence Platform
```

Optional reverse delegation:

```text
Project Intelligence Platform
     │
     ├── A2A
     ├── supported CLI
     └── supported API
            ↓
     External Strong Agent
```

Reverse integration must use officially supported interfaces of the target system.

---

# 52. Task Context Bundles

For complex tasks:

```text
build_context("Implement REQ-471")
```

may produce:

```text
TaskContext
├── requirement
├── relevant OpenSpec
├── Wiki sections
├── source code
├── interfaces
├── dependencies
├── architecture constraints
├── graph neighbourhood
├── tests
└── Git diff
```

Task Context Bundles are ephemeral transport artifacts and are not canonical knowledge.

---

# 53. OpenSpec Integration

OpenSpec is first-class.

Maintain traceability:

```text
Business Requirement
        ↓
OpenSpec Change
        ↓
Specification
        ↓
Architecture Decision
        ↓
Component
        ↓
Implementation
        ↓
Test
```

---

# 54. Knowledge Provenance

Knowledge states may include:

- verified;
- inferred;
- assumption;
- conflicting;
- stale;
- unknown.

Every durable fact should retain evidence/source information.

The system must distinguish human/source-derived facts from LLM-generated interpretations.

---

# 55. Knowledge Freshness

When source code or documents change:

```text
changed source
     ↓
dependency/provenance analysis
     ↓
affected knowledge
     ↓
mark stale / regenerate candidates
     ↓
verify
     ↓
materialize durable update
```

Avoid uncontrolled rewriting of authoritative knowledge.

---

# 56. Enterprise Security Boundary

Local access and external transmission are separate permissions.

```text
Project Context
      ↓
Policy / DLP / Secret Filter
      ↓
External Agent
```

Support:

- secret detection;
- source-level permissions;
- security classification;
- outbound filtering;
- redaction;
- egress policy;
- auditability.

Security metadata participates in retrieval filtering.

---

# 57. Human Interfaces and Frontend Strategy

The platform shall provide human-facing access independently of Claude Code, Codex, OpenCode or another external coding harness.

The system must therefore support a standalone project UI for:

- asking project questions;
- inspecting retrieved evidence;
- browsing Wiki knowledge;
- navigating graph relations;
- inspecting requirements and OpenSpec traceability;
- viewing current Git/project version;
- triggering source refresh;
- viewing indexing status;
- inspecting stale/conflicting knowledge;
- launching approved knowledge materialization;
- optionally delegating complex tasks through the Query Orchestrator.

The frontend is a replaceable adapter and must not become a core architectural dependency.

## 44.1 Frontend Option A — Custom Lightweight UI

The preferred default option is a small project-specific frontend implemented with a lightweight permissively licensed framework.

A suitable candidate is Ionic Framework or another equivalent framework that passes the project license policy.

The custom UI should:

- remain intentionally small;
- use the platform REST/API layer;
- optionally consume streaming responses;
- expose only project-specific functionality;
- avoid bundling a second AI platform;
- be compiled into static frontend assets where possible;
- be served directly by the main Project Intelligence backend/container.

Conceptually:

```text
Browser
   ↓
Custom UI
   ↓
REST / streaming API
   ↓
Project Intelligence Platform
```

A production build should not require Node.js or frontend development tooling on the target developer machine.

Build tooling may be used during image creation, while runtime deployment should contain only the generated assets and backend runtime.

## 44.2 Frontend Option B — Open WebUI Integration

Open WebUI may be supported as an optional ready-made frontend profile.

Conceptually:

```text
Browser
   ↓
Open WebUI
   ↓
Project Intelligence API / compatible adapter
   ↓
Query Orchestrator
   ↓
Retrieval / Local LLM / External Agent
```

Open WebUI must not be a mandatory core dependency.

Its exact version and license must pass the same dependency/license governance as every other bundled component.

Because Open WebUI licensing can differ between versions and may include branding or commercial-distribution conditions, the selected version must be validated before:

- bundling;
- white-labeling;
- redistribution;
- commercial sale;
- large-enterprise deployment.

Therefore Open WebUI belongs to an optional deployment profile rather than the license-critical core architecture.

## 44.3 UI-Abstraction Boundary

The backend should expose a stable UI-facing API so frontend implementations remain replaceable.

For example:

```text
Project UI API
├── query
├── retrieve
├── sources
├── graph
├── wiki
├── project-version
├── indexing-status
├── knowledge-status
├── materialize
└── agent-delegation
```

This allows:

```text
Custom Ionic UI
Open WebUI
future desktop UI
future IDE UI
```

to reuse the same core platform.

## 44.4 No Coding Harness Required

The standalone UI must be fully usable without:

- Claude Code;
- Codex;
- OpenCode;
- Hermes;
- an IDE agent.

For simple questions, the UI can use:

```text
Retrieval
    ↓
Context Assembler
    ↓
direct structured answer
```

or:

```text
Retrieval
    ↓
small local LLM
    ↓
answer
```

Only complex tasks should be escalated to a strong external agent when such integration is configured.

---

# 58. One-Click / Near-Zero-Setup Distribution

Portability is a primary product requirement.

The target experience should be closer to:

```text
download
→ start
→ open browser
```

than to a multi-step developer installation.

The project should provide one or more launch experiences such as:

```text
Windows:
ProjectIntelligence.exe
or
Start-ProjectIntelligence.ps1

Linux:
./project-intelligence

Container environments:
docker compose up
```

The launcher may internally:

1. verify Docker/Podman or bundled runtime availability;
2. create required volumes;
3. mount the project repository;
4. start the container(s);
5. wait for health readiness;
6. open the browser automatically;
7. display the local URL and status.

The user should not need to manually start databases, model servers or frontend development servers.

## 45.1 Single-Container Default

Preferred packaging:

```text
Container 1
├── backend
├── runtime DB
├── retrieval engine
├── MCP
├── A2A
├── REST
├── embedding runtime
├── optional small local LLM
└── custom static frontend
```

The frontend should be served by the same container whenever practical.

## 45.2 Optional Two-Container Profile

A second container is acceptable when using:

- isolated local model runtime;
- Open WebUI;
- another optional UI/runtime integration.

Example:

```text
Container 1
Project Intelligence Core

Container 2
Optional UI or Model Runtime
```

The second container must remain optional.

## 45.3 Distribution Profiles

Recommended profiles:

```text
core-headless
    MCP + REST + CLI only

desktop-lite
    core + built-in lightweight UI

desktop-local-ai
    core + built-in UI + local small LLM

open-webui
    core + optional Open WebUI integration

enterprise
    core + policy/security integrations + optional external storage
```

All profiles should share the same canonical project data model.

---


# 59. Management / Control Plane and Micro-Feature Extension Architecture

The standalone frontend shall evolve from a search/chat surface into the **Management / Control Plane** of the Project Intelligence Platform.

The architecture shall explicitly separate:

```text
Control Plane
    = configuration, policies, permissions, plugin/feature lifecycle,
      hooks, secret references, environment mappings, diagnostics,
      audit, health and administration

Data Plane
    = ingestion, indexing, retrieval, graph operations, context assembly,
      MCP tool execution, A2A requests and runtime agent operations
```

The Web UI and administrative CLI belong to the Control Plane.

The ingestion/retrieval/runtime services belong to the Data Plane.

The Control Plane configures and observes the Data Plane but must not bypass the same authorization rules that apply to agents and plugins.

## Control Plane Capabilities

The UI should be extensible to manage:

- active project and Git version;
- source configuration;
- `tmp/local/source` ingestion;
- indexing and embedding status;
- retrieval profiles;
- model/runtime configuration;
- MCP and A2A endpoint status;
- agent adapters;
- plugins and micro-features;
- hook definitions;
- hook permissions and failure policy;
- read/write capabilities;
- secret references;
- environment-variable mappings;
- feature flags;
- policy rules;
- approval requests;
- audit logs;
- operational logs;
- stale/conflicting knowledge;
- dependency/license status;
- health and diagnostics.

The UI is only one client of these administrative APIs. CLI or enterprise automation must be able to use the same application services.

## Architectural Style

The recommended extension style is:

```text
Hexagonal / Ports-and-Adapters Core
            +
Micro-Kernel / Plugin Extension Surface
```

The core remains one modular deployable application.

Optional capabilities are connected through stable extension ports rather than being compiled into business logic or split into separate microservices by default.

Conceptually:

```text
                    Project Intelligence Core
                              │
                     Stable Extension API
                              │
       ┌──────────────────────┼───────────────────────┐
       ↓                      ↓                       ↓
   Hook Plugin          Secret Provider        Source Adapter
       ↓                      ↓                       ↓
 Agent Policy           Observability          Export Adapter
       ↓                      ↓                       ↓
 UI Extension          Enterprise Auth         Custom Feature
```

A micro-feature should become a plugin only when it has a coherent capability, independent lifecycle/configuration, and meaningful enable/disable value.

The system must not turn every internal class or service into a plugin.

## Feature / Plugin Registry

The runtime shall maintain a registry for built-in and installed features.

Example manifest:

```yaml
id: project-intelligence.audit-export
name: Audit Export
version: "1.2.0"
apiVersion: "1"
license: Apache-2.0
provider: project-intelligence
type: plugin

capabilities:
  - audit.read
  - export.write

configurationSchema: schemas/audit-export.schema.json

permissions:
  required:
    - audit.read
  optional:
    - filesystem.write

hooks:
  - afterMcpTool
  - afterAgentDelegation

ui:
  settingsPanel: true
  statusPanel: true
```

Possible lifecycle states:

```text
installed
enabled
disabled
failed
incompatible
blocked-by-policy
update-available
```

The Control Plane can inspect, enable, disable and configure these features.

## Stable Plugin API

The plugin surface should be versioned and may expose contracts such as:

```text
Plugin
FeatureProvider
HookProvider
SourceProvider
SecretProvider
PolicyProvider
AgentAdapter
UiExtension
ObservabilityProvider
Exporter
```

Logical lifecycle:

```text
discover
   ↓
validate manifest
   ↓
verify compatibility
   ↓
verify license
   ↓
verify requested permissions
   ↓
load/start
   ↓
health check
   ↓
enable
```

Plugins must not query or mutate internal runtime database tables directly.

They interact through application-owned ports and APIs.

## Trusted vs Isolated Plugins

At least two trust modes should be possible.

### Trusted In-Process Plugin

For project-owned/built-in low-risk extensions.

Advantages:

- lowest latency;
- simplest packaging;
- easiest one-container deployment.

Risk:

- code executes in the main process trust boundary.

### Isolated Plugin / Sidecar

For:

- third-party plugins;
- plugins requiring foreign runtimes;
- higher-risk integrations;
- extensions requiring stronger resource/network isolation.

Conceptually:

```text
Project Intelligence Core
         │
         │ authenticated local protocol
         ↓
Plugin Sidecar / Sandbox
```

Possible future isolation technologies:

- restricted subprocess;
- secondary container;
- WASM;
- OS sandbox.

The default installation must not require this complexity for ordinary built-in features.

## Capability-Based Permissions

Agents, plugins and hooks must receive explicit capabilities rather than unrestricted application/database access.

Example capabilities:

```text
knowledge.read
knowledge.write
knowledge.materialize

retrieval.query
retrieval.admin

graph.read
graph.write

source.read
source.import

filesystem.read
filesystem.write

git.read
git.write

config.read
config.write

secret.reference
secret.resolve

mcp.invoke
mcp.admin

agent.delegate

network.local
network.external

audit.read
audit.write
```

The same capability vocabulary should be usable for:

- UI users;
- coding agents;
- A2A agents;
- plugins;
- hooks;
- CLI operations;
- automation.

## Roles and Policy Resolution

Human/operator roles may provide convenient defaults:

```text
Viewer
Developer
Maintainer
Administrator
```

but authorization should resolve to capabilities.

Conceptually:

```text
identity
   +
role
   +
requested operation
   +
resource
   +
project/version context
       ↓
Policy Engine
       ↓
ALLOW / DENY / REQUIRE_APPROVAL
```

A future ABAC layer may also consider:

- branch;
- source classification;
- plugin identity;
- agent identity;
- environment;
- network destination;
- operation risk.

## First-Class Hook System

Hooks shall be managed extension points rather than arbitrary unrestricted code execution.

Potential lifecycle events:

```text
beforeIngestion
afterIngestion

beforeIndexUpdate
afterIndexUpdate

beforeRetrieval
afterRetrieval

beforeContextAssembly
afterContextAssembly

beforeMcpTool
afterMcpTool

beforeAgentDelegation
afterAgentDelegation

beforeMaterialization
afterMaterialization

onBranchSwitch
onProjectOpen
onProjectClose
```

Each hook definition should include:

```text
hook id
plugin id
event
priority
timeout
permissions
failure policy
configuration
version
```

## Hook Failure Policy

Supported policies may include:

```text
FAIL_OPEN
FAIL_CLOSED
WARN_ONLY
DISABLE_PLUGIN
```

Security-sensitive hooks should normally fail closed.

Observability-only hooks can normally fail open.

Every hook invocation should support:

- timeout;
- cancellation;
- structured result;
- correlation ID;
- audit record;
- bounded retries if explicitly configured.

A failed hook must not silently deadlock MCP/retrieval execution.

## Agent Read-Only Hook / Runtime Context Use Case

Coding agents should not read internal DB tables.

Example:

```text
Coding Agent
     │
     │ MCP
     ↓
project.get_runtime_context
     │
     ↓
Policy Engine
     │
     ↓
Read-Only Runtime Configuration Port
     │
     ↓
effective configuration
```

Example capability assignment for a read-only coding agent:

```text
knowledge.read      = allow
retrieval.query     = allow
config.read         = allow
audit.write         = allow

knowledge.write     = deny
knowledge.materialize = deny
config.write        = deny
git.write           = deny
secret.resolve      = deny unless explicitly scoped
```

This allows an agent to consume runtime configuration and emit audit/log events while preventing durable writes.

## Configuration Scopes

Configuration should be separated into four scopes.

### Git-Versioned Project Configuration

Examples:

- project feature declarations;
- hook definitions;
- retrieval profiles;
- non-secret source policies;
- non-secret plugin configuration.

This configuration follows the Git project version.

### Local Machine Configuration

Examples:

- local ports;
- model cache paths;
- Docker/Podman choice;
- local UI preferences.

Not normally committed.

### Secret Configuration

Examples:

- API tokens;
- passwords;
- private keys;
- credentials.

Never stored directly in Git Portable Knowledge.

### Runtime / Session Configuration

Examples:

- temporary feature overrides;
- active agent session;
- working-tree overlay;
- temporary hook state.

Ephemeral by default.

## Secret and Environment Variable Management

The Control Plane may manage secret **references and mappings**, but the runtime database must not become a plain-text secret vault.

Preferred design:

```text
UI / CLI
    ↓
Secret Configuration
    ↓
SecretProvider Port
    ↓
OS keychain / environment / encrypted local store / enterprise vault
```

Store references such as:

```text
secret://local/confluence-token
secret://enterprise/internal-api-key
env://HTTP_PROXY
```

instead of raw values in Git knowledge.

Environment mappings may be injected into an agent/plugin process at controlled launch time:

```yaml
runtimeEnvironment:
  PROJECT_INTELLIGENCE_ENDPOINT:
    value: "http://127.0.0.1:7777"

  CONFLUENCE_TOKEN:
    source: secret://local/confluence-token
```

Secrets must be redacted from:

- Git serialization;
- MCP responses;
- A2A payloads unless explicitly authorized;
- UI logs;
- audit payloads;
- LLM context.

## Central Policy Engine

Authorization logic shall be centralized.

Sensitive execution paths consult the same Policy Engine:

```text
MCP tool
A2A request
REST request
plugin
hook
agent delegation
materialization
Git write
secret resolution
external network request
```

Conceptually:

```text
request
 + actor identity
 + capability
 + target resource
 + project/version context
        ↓
Policy Engine
        ↓
ALLOW / DENY / REQUIRE_APPROVAL
```

Plugins must not implement independent shadow authorization systems for core resources.

## Approval Gates

High-impact actions may return:

```text
REQUIRE_APPROVAL
```

Typical examples:

- durable knowledge materialization;
- Git write;
- external data transmission;
- resolving sensitive secrets;
- enabling a third-party plugin;
- granting `network.external`;
- running a privileged hook.

The Control Plane can present and record approval decisions.

## Audit vs Operational Logs

Two streams should remain separate.

```text
Operational Log
    = diagnostics, errors, performance, health

Audit Log
    = security/state-relevant actions and decisions
```

Audit events should include fields such as:

```text
timestamp
correlationId
projectVersion
actorType
actorId
plugin/agentId
operation
resource
policyDecision
result
duration
```

Secret values and unnecessary source contents must never be written into audit records.

## Observability Plugins

The core should emit structured events through observability ports.

Optional plugins can export to:

- local structured files;
- OpenTelemetry;
- metrics systems;
- tracing systems;
- enterprise logging infrastructure.

The core must not depend on one observability vendor.

## Feature Flags

Micro-features may use states such as:

```text
disabled
enabled
experimental
deprecated
```

Feature state may be scoped by:

- machine;
- project;
- branch;
- user;
- deployment profile.

Git-versioned feature declarations and local overrides must remain distinct.

## UI Plugin Management

The Control Plane should be able to present:

```text
Plugins
├── Installed
├── Available
├── Disabled
└── Incompatible
```

For each plugin:

```text
name
version
license
publisher
status
requested capabilities
granted capabilities
hooks
configuration
health
logs
update information
```

Before enabling a plugin, the UI should present requested permissions.

Example:

```text
Plugin: Confluence Synchronizer

Requests:
✓ source.read
✓ knowledge.write
✓ network.external
✓ secret.reference

Does not request:
✗ git.write
✗ config.write
```

## UI Contributions from Plugins

Plugins may contribute controlled UI modules such as:

- settings pages;
- status cards;
- diagnostics;
- source configuration panels;
- graph visualizations;
- custom administration panels.

Prefer declarative UI-extension descriptors.

Arbitrary third-party JavaScript injection into the primary UI should not be allowed unless the plugin is explicitly trusted.

## Plugin Sources and Distribution

Plugins may eventually be installable from:

- local directory;
- signed archive;
- Git repository;
- enterprise catalog.

A public marketplace is not required initially.

Every plugin package participates in:

- license checks;
- compatibility checks;
- integrity/signature checks;
- permission review;
- security scanning.

## Administrative API Boundary

Administrative operations should use separate scopes from ordinary agent-facing operations.

Conceptually:

```text
admin.features.*
admin.plugins.*
admin.hooks.*
admin.policies.*
admin.secretReferences.*
admin.audit.*
admin.health
admin.capabilities
```

Ordinary coding agents should not receive these permissions by default.

The agent-facing MCP API may share underlying application services but uses a restricted authorization profile.

## Updated Control Plane / Data Plane View

```text
                                  Operator
                                     │
                                     ▼
                           ┌──────────────────┐
                           │   Web UI / CLI   │
                           │   CONTROL PLANE  │
                           └────────┬─────────┘
                                    │
                 ┌──────────────────┼────────────────────┐
                 ▼                  ▼                    ▼
          Feature Registry      Policy Engine      Config/Secrets
                 │                  │                    │
                 ├──────────┬───────┴────────┬───────────┤
                 ▼          ▼                ▼           ▼
              Plugins     Hooks          Audit       Agent Adapters
                 │          │                │           │
                 └──────────┴────────┬───────┴───────────┘
                                     │
                                     ▼
                         ┌────────────────────────┐
                         │       DATA PLANE       │
                         │                        │
                         │ Ingestion              │
                         │ Runtime Knowledge DB   │
                         │ Retrieval              │
                         │ Knowledge Graph        │
                         │ Context Assembler      │
                         │ MCP / A2A              │
                         └────────────┬───────────┘
                                      │
                          ┌───────────┴────────────┐
                          ▼                        ▼
                     Coding Agents              Humans
```

# 60. Deployment Model

Preferred developer deployment:

```text
┌────────────────────────────────────────────┐
│ Project Intelligence Container             │
│                                            │
│ Git / Version Manager                      │
│ Ingestion Engine                           │
│ tmp/local/source Adapter                   │
│ Structured Code Intelligence               │
│ Java/JAR Analyzer                          │
│ Documentation Adapters                     │
│ OpenSpec Adapter                           │
│ Wiki Engine                                │
│ Graph Builder                              │
│ Embedded Runtime Working DB                │
│ Full-text / Sparse Index                   │
│ Dense Vector Index                         │
│ Metadata Index                             │
│ Embedding Runtime                          │
│ Optional Small Local LLM                   │
│ Retrieval Engine                           │
│ Context Assembler                          │
│ Query Orchestrator                         │
│ Feature / Plugin Registry                  │
│ Hook Runtime                               │
│ Policy Engine                              │
│ Secret Provider Abstraction                │
│ Audit / Observability                      │
│ MCP Server                                 │
│ A2A Adapter / Agent Endpoint                │
│ REST API                                   │
│ CLI                                        │
│ Embedded Web UI                            │
└────────────────────────────────────────────┘
```

External mounts:

```text
repository
runtime cache
model cache
optional external source directories
```

Preferred startup:

```text
project-intelligence start
```

or:

```text
docker compose up
```

An optional second container may isolate the model runtime.

---

# 61. Runtime Storage Strategy

The initial implementation should prefer one embedded runtime storage solution capable of supporting as much as practical of:

- relational metadata;
- full-text search;
- vector search;
- graph traversal.

If no single embedded engine satisfies the requirements cleanly, a small set of embedded components may be used **inside the same deployable unit**.

Avoid mandatory external infrastructure such as:

- Elasticsearch;
- Neo4j;
- Qdrant;
- PostgreSQL;

for the default desktop deployment.

Enterprise-scale profiles may optionally replace embedded components.

---

# 62. Startup / Branch-Switch Synchronization

Conceptual flow:

```text
1. Detect repository.
2. Resolve HEAD and working-tree state.
3. Load canonical manifests for current Git state.
4. Compare canonical shard hashes with runtime cache.
5. Drop/invalidate runtime entries not valid for the target state.
6. Hydrate missing/changed canonical shards.
7. Discover changed code/resources.
8. Scan tmp/local/source recursively.
9. Parse only new/changed sources.
10. Rebuild only affected graph entities/relations.
11. Recompute only missing embeddings.
12. Refresh sparse/full-text/vector indexes.
13. Apply working-tree overlay.
14. Detect stale durable knowledge.
15. Start/continue MCP, A2A, REST and UI services.
```

Switching branches should be an incremental reconciliation operation, not a mandatory full rebuild.

---

# 63. Durable Knowledge Save / Commit Flow

When the developer decides that runtime-enriched knowledge should become durable:

```text
1. Select durable runtime changes.
2. Exclude LOCAL_ONLY sources/data.
3. Normalize entities and relations.
4. Serialize deterministically.
5. Re-shard affected knowledge only.
6. Update manifests and hashes.
7. Regenerate affected Wiki pages if configured.
8. Validate provenance and references.
9. Validate license/security policy.
10. Produce Git diff.
11. Optional human/agent review.
12. Commit with the project branch.
```

This gives the database a Git-versioned portable representation without committing the database file itself.

---

# 64. Suggested Repository Layout

```text
project/
│
├── src/
├── pom.xml
├── openspec/
├── docs/
├── requirements/
│
├── tmp/
│   └── local/
│       └── source/              # dynamic local ingestion inbox
│
├── project-knowledge/
│   ├── wiki/
│   ├── graph/
│   │   ├── nodes/
│   │   └── edges/
│   ├── chunks/
│   ├── sources/
│   ├── objects/
│   │   ├── 00/
│   │   ├── 01/
│   │   └── ...
│   └── manifests/
│       ├── knowledge-schema.yaml
│       ├── source-manifest.yaml
│       ├── graph-manifest.yaml
│       └── chunk-manifest.yaml
│
├── platform/
│   ├── plugins/
│   ├── hooks/
│   ├── policies/
│   └── schemas/
│
├── distribution/
│   ├── skills/
│   │   └── project-intelligence/
│   ├── codex/
│   ├── claude-code/
│   ├── opencode/
│   └── generic-agent/
│
└── project-context.yaml
```

Runtime cache:

```text
.project-intelligence-cache/
├── runtime.db
├── vector-index/
├── fts/
├── graph-index/
├── embeddings/
└── model-cache/
```

Normally Git-ignored:

```text
tmp/local/**
.project-intelligence-cache/**
```

---

# 65. License-Aware Configuration Example

```yaml
licensing:
  mode: strict
  allow:
    - Apache-2.0
    - MIT
    - BSD-2-Clause
    - BSD-3-Clause
    - ISC
  review:
    - MPL-2.0
    - EPL-2.0
    - LGPL-2.1-only
    - LGPL-3.0-only
  denyPatterns:
    - "*-NC-*"
    - "research-only"
    - "non-commercial"
    - "source-available-restricted"
```

The exact allow/review policy remains a legal/product configuration, not hard-coded domain logic.

---

# 66. Source Configuration Example

```yaml
sources:
  localInbox:
    path: tmp/local/source
    recursive: true
    defaultPolicy: LOCAL_ONLY

  externalDocumentation:
    path: external-documentation
    recursive: true
    defaultPolicy: SNAPSHOT

  confluence:
    enabled: false

  intranet:
    enabled: false
```

---

# 67. Runtime Synchronization Contract

Conceptually:

```text
restore_runtime(projectVersion)
ingest_sources(sourceSet)
update_indexes()
retrieve_context(query)
materialize_durable_changes()
```

The architecture must preserve a clear boundary between:

```text
runtime-only state
```

and:

```text
durable Git-versioned knowledge
```

---

# 68. Architectural Invariants

1. **Git is the source of truth for durable versioned project knowledge.**
2. **The runtime DB is an active working knowledge store, not a committed artifact.**
3. **Runtime DB ↔ Git Portable Knowledge synchronization is bidirectional.**
4. **Canonical serialization must be deterministic and round-trip safe.**
5. **Canonical knowledge is sharded and content-addressable for Git scalability.**
6. **`tmp/local/source` is a recursive dynamic ingestion inbox and is local-only by default.**
7. **Local inputs can be promoted to canonical snapshots only through explicit source policy.**
8. **Runtime state is incrementally reconstructed when Git branches/commits change.**
9. **Content hashes are reused across branches to avoid redundant parsing/vectorization.**
10. **Structured code intelligence complements, rather than replaces, vector retrieval.**
11. **JARs are first-class knowledge sources.**
12. **ANN graphs and semantic Knowledge Graphs are different structures.**
13. **Hybrid dense + sparse retrieval is the default.**
14. **Metadata enforces version, security and correctness constraints.**
15. **Contextualized chunks improve semantic retrieval quality.**
16. **Graph/hierarchy expansion enriches candidate evidence.**
17. **Context Assembler owns the final bounded context.**
18. **The system follows retrieval-first escalation before expensive LLM scanning.**
19. **The small local LLM is an optional inexpensive worker, not the primary architect/programmer.**
20. **Query Orchestrator owns delegation decisions.**
21. **MCP exposes tools/context to coding agents.**
22. **A2A exposes agent-to-agent collaboration when agent capability is enabled.**
23. **MCP and A2A are complementary interfaces.**
24. **OpenSpec is a first-class intent and traceability layer.**
25. **Knowledge provenance and staleness are explicit.**
26. **External transmission is security-policy controlled.**
27. **All bundled dependencies and model assets have known licenses.**
28. **Permissive commercial-use-friendly licenses are preferred.**
29. **Restricted/non-commercial dependencies cannot silently enter the default stack.**
30. **The default deployment remains one container, with at most one optional UI/model-runtime container.**
31. **The platform must provide a standalone human UI mode that does not require an external coding harness.**
32. **The default built-in frontend should remain lightweight and be served from the core deployment where practical.**
33. **Open WebUI is an optional replaceable integration and must pass the same license/distribution gate as every dependency.**
34. **Installation should target one-click or near-zero-setup startup, not a developer-only multi-command procedure.**
35. **No specific LLM, vector DB, graph DB, reranker, frontend or agent vendor is architecturally mandatory.**
36. **The canonical Agent Skill is versioned, license-declared and generated into all vendor plugin packages.**
37. **The MCP server is a canonical skill-distribution source, while adapters handle clients that require install-time snapshots.**
38. **Skill version and MCP API version compatibility is machine-checkable.**
39. **The human-readable Wiki supports an OKF v0.2 profile without coupling the core runtime model to OKF internals.**
40. **Agent-specific plugin packages are generated from shared sources and cannot own project-domain logic.**
41. **Codex/ChatGPT, Claude Code and OpenCode receive first-class distribution profiles; other agents use generic MCP + Agent Skill + optional A2A integration.**
42. **Skill/plugin packages are supply-chain artifacts and must pass integrity, license and security gates.**
43. **Agent integration behaviour is regression-tested for retrieval-first operation, token efficiency and version correctness.**
44. **The built-in Web UI is a Control Plane, not merely a chat/search page.**
45. **Control Plane and Data Plane responsibilities remain explicitly separated.**
46. **Plugins use stable extension ports and never depend directly on internal runtime DB tables.**
47. **Plugins, hooks and agents operate under explicit capability-based authorization.**
48. **Secrets are resolved through Secret Providers and never serialized into Git knowledge or logs.**
49. **Hook execution is bounded by timeout, failure policy, permissions and auditability.**
50. **High-impact operations may require explicit operator approval.**
51. **Third-party plugins may be isolated in a sidecar/sandbox without forcing that complexity on built-in features.**
52. **The application remains a modular core with a micro-kernel extension surface, not a fleet of microservices.**


---

# 69. Final High-Level Architecture

```text
                           Git Repository
                                  │
       ┌──────────────────────────┼─────────────────────────┐
       │                          │                         │
     Source                    OpenSpec             Portable Knowledge
       │                          │                sharded + manifests
       │                          │                         │
       └──────────────┬───────────┴──────────────┬─────────┘
                      │                          │
                      │                    import/export
                      │                          ↕
              tmp/local/source          Runtime Working DB
                      │                          │
                      └──────────┬───────────────┘
                                 ↓
                         Ingestion / Sync
                                 ↓
                    Code + JAR + Document Intelligence
                                 ↓
                         Knowledge Model
                    Wiki + Entities + Relations
                                 ↓
                  ┌──────────────┼──────────────┐
                  ↓              ↓              ↓
              Sparse/BM25     Dense ANN     Metadata
                  └──────────────┼──────────────┘
                                 ↓
                          Hybrid Retrieval
                                 ↓
                          Graph Expansion
                                 ↓
                       Hierarchy Expansion
                                 ↓
                             Rerank
                                 ↓
                        Context Assembler
                                 ↓
                        Query Orchestrator
                 ┌───────────────┼────────────────┐
                 ↓               ↓                ↓
          Direct Retrieval   Small Local LLM   Strong Agent
                                                   ↑
                                            A2A / API / CLI
                                 ↓
                 MCP / A2A / REST / CLI / Web UI
                                 ↓
                 Claude Code / Codex / OpenCode / Humans
```

---

# 70. Next Detailed Design Stage

The next stage should define concrete schemas for:

```text
Source
SourcePolicy
Document
Section
Chunk
ContextualChunk
Metadata
Entity
Relation
Evidence
KnowledgeState
ProjectVersion
Shard
Manifest
RuntimeChange
TaskContext
```

and precise contracts for:

```text
restore_runtime(projectVersion)
refresh_sources()
retrieve_context(query, filters, purpose, contextBudget)
materialize_durable_changes()
switch_project_version(gitState)

describe_capabilities()
publish_skill(skillVersion)
verify_skill_server_compatibility()
package_agent_plugin(targetAgent)
install_agent_adapter(targetAgent)
validate_okf_bundle()

list_features()
configure_feature(featureId)
evaluate_policy(identity, capability, resource)
register_hook(hookDefinition)
execute_hook(event)
resolve_secret_reference(secretRef)
search_audit_log(query)
```

The exact storage product should be selected **after** these contracts are defined.

Storage technology must serve the architecture, not define it.

---


# 71. Architect Review Outcome

The architecture has been reviewed from two complementary perspectives.

## 0.1 General Software Architecture Review

Key strengths:

- strong separation of canonical and runtime state;
- Git-native versioning;
- portable deployment;
- replaceable retrieval technologies;
- incremental/content-addressed processing;
- explicit security and license governance.

Primary improvements incorporated by this revision:

- formal Ports-and-Adapters boundary for agent ecosystems;
- protocol/version compatibility contract;
- plugin generation instead of manually diverging integrations;
- one-click install/uninstall contract;
- deterministic capability discovery;
- explicit integration/evaluation quality gates.

## 0.2 AI / Agent Architecture Review

Primary improvements incorporated:

- versioned Agent Skill as a first-class product artifact;
- MCP-hosted skill distribution resources;
- snapshot/runtime distribution distinction;
- Agent Skills metadata and progressive-disclosure structure;
- OKF v0.2 Wiki profile;
- retrieval-first behaviour encoded in the skill;
- tool/context responsibilities separated from skill workflow guidance;
- plugin packages for Codex/ChatGPT, Claude Code and OpenCode;
- security/integrity controls around skill/plugin distribution.

No blocking architectural ambiguity remains at this foundation stage. Product-specific implementation choices can be deferred behind ports and configuration, so an additional requirements interview is not required before the next detailed design stage.

---

# 72. Final Design Intent

The desired result is not merely a vector database, Wiki generator, MCP server or local chatbot.

It is a **portable, Git-native project intelligence runtime** that:

- understands code and business documentation;
- tracks project versions;
- restores the correct knowledge state for a Git branch/commit;
- incrementally ingests additional local and external knowledge;
- uses embeddings, lexical search, graph relations and metadata before expensive LLM reasoning;
- exposes compact, high-quality project context to coding agents;
- can act as an A2A-compatible project agent;
- can persist approved knowledge back into Git-friendly structures;
- can be used and redistributed in commercial environments with controlled dependency licensing;
- provides a standalone lightweight browser UI without requiring a coding harness;
- optionally integrates a ready-made UI such as Open WebUI when licensing and packaging constraints allow it;
- targets one-click or near-zero-setup startup and distribution;
- remains lightweight enough to run locally as one or two containers;
- publishes a canonical, versioned Agent Skill together with the MCP integration contract;
- exposes skill distribution metadata/resources from the MCP server;
- supports an OKF-compatible Git Wiki profile;
- generates first-class plugin/integration bundles for Codex/ChatGPT, Claude Code and OpenCode;
- remains compatible with generic MCP + Agent Skills clients without requiring a vendor-specific plugin.


---

# Current Standards / Ecosystem Basis (reviewed 2026-10-02)

The architectural integration decisions above were checked against the then-current public specifications/documentation for:

- Agent Skills specification (`SKILL.md`, metadata, progressive disclosure);
- OpenAI Plugins / Codex portable plugin packaging and MCP-backed skills;
- Anthropic Agent Skills and Claude Code plugin packaging;
- OpenCode plugins and MCP configuration;
- Google Open Knowledge Format v0.2.

These are treated as external evolving integration contracts. Their details belong in adapters/build tooling rather than the Project Intelligence core.


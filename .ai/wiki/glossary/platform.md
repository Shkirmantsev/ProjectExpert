---
id: glossary.platform
title: Platform Glossary
kind: glossary
status: draft
summary: Vocabulary used by the v0.8 Project Intelligence Platform.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md
  - openspec/changes/plan-v0-8-platform-architecture/proposal.md
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
`assumption`, `conflicting`, `stale`, `unknown`.

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
`DENY` or `REQUIRE_APPROVAL`.

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
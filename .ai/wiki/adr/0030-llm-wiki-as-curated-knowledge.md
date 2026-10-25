---
id: adr.0030-llm-wiki-as-curated-knowledge
title: LLM Wiki as the curated knowledge layer
kind: adr
status: accepted
date: 2026-10-25
summary: Separate derived knowledge (parsed, chunked, embedded, rebuilt) from curated knowledge (LLM Wiki); the calling LLM writes curated OKF pages through MCP without an approval id, every write validated against OKF v0.2 and audited in the reserved log.
sourceRefs:
  - pi_platform/core/wiki/llm_wiki.py
  - pi_platform/mcp/server.py
  - pi_platform/mcp/tool_schemas.py
  - openspec/specs/2026-10-11-okf-wiki-profile-distribution/spec.md
related:
  - adr.0002-canonical-runtime-separation
  - adr.0029-portable-model-runtime-and-oci-kit
  - modules.llm-wiki
  - interfaces.mcp-tools
maintenance:
  mode: authored
---

# ADR 0030 — LLM Wiki as the curated knowledge layer

## Context

The platform's canonical knowledge is derived: sources are parsed,
chunked, embedded and rebuilt from the repository. That pipeline
captures *what* the code says but not *why* it looks the way it
does — design intent, operator conventions, decisions taken after
review. A calling LLM discovers such knowledge while working on a
project, and previously had no sanctioned place to record it:
the derived-knowledge write tools (`project.materialize_knowledge`,
`project.refresh_sources`) are gated behind a trusted-operator
`approval_id` because they rewrite materialised derived state.

At the same time the OKF v0.2 bundle
(`project-knowledge/wiki/`) already defines a Git-versioned,
human-readable Wiki layer with reserved `index.md` / `log.md`
semantics. Writing to it ad hoc (raw file edits by agents) would
bypass validation, audit and path safety.

## Decision

1. **Two knowledge layers, kept separate.** Derived knowledge
   (parsed, chunked, embedded, indexed, rebuilt) and curated
   knowledge (the LLM Wiki) are distinct layers with distinct
   write paths. Curated knowledge lives in the Git-versioned OKF
   v0.2 bundle; derived knowledge stays behind the canonical /
   runtime sync. Neither layer impersonates the other.
2. **The calling LLM writes curated pages through MCP.** Five
   tools expose the layer: `project.wiki_list_pages`,
   `project.wiki_read_page`, `project.wiki_search`,
   `project.wiki_write_page`, `project.wiki_validate`. The
   intended loop is search the project, read the curated pages,
   write what was learned, then validate the bundle.
3. **Curated writes need no approval id.** A curated page is
   additive knowledge, not derived materialisation: it cannot
   rewrite canonical shards, indexes or manifests, so it does not
   cross the trusted-operator boundary. The derived-knowledge
   write tools keep requiring `approval_id`.
4. **Every write is validated and audited.** The page is
   rendered with OKF frontmatter and validated against the OKF
   v0.2 profile BEFORE storage (an invalid page is never
   written); the write is atomic and path-safe (a page cannot
   escape the Wiki root); it is recorded in the reserved
   `log.md`; and the navigation index is refreshed. A written
   page joins the searchable corpus on the next project refresh.

## Consequences

- A calling LLM can accumulate durable project understanding
  without operator intervention on every page, while malformed,
  non-OKF or path-escaping pages are rejected by the platform
  rather than by review luck.
- The audit trail (`log.md`) plus Git history makes curated
  knowledge reviewable and revertable like any other file.
- Curated knowledge is only as trustworthy as the model that
  wrote it; validation proves OKF conformance, not factual
  correctness. Retrieval must keep curating provenance visible so
  a reader can distinguish a curated explanation from a
  canonical requirement.
- Searchability lags the write by one refresh: the dense index
  picks the page up on the next project refresh, while
  `project.wiki_search` (text overlap over the bundle) sees it
  immediately.
- The reserved `index.md` / `log.md` remain platform-owned;
  callers cannot forge the navigation or erase the audit trail
  through the write tool.

## Alternatives

- **Reuse the approval-gated materialise path for Wiki writes.**
  Rejected: it would require an operator grant for every curated
  page and would blur the boundary between additive knowledge and
  derived materialisation, which the approval boundary exists to
  protect.
- **Let agents edit `project-knowledge/wiki/` directly.**
  Rejected: no pre-store validation, no atomicity guarantee, no
  path containment, no audit entry, and no guarantee the
  navigation index stays in sync.
- **Store curated knowledge as derived state (graph facts or
  index entries).** Rejected: curated statements are explanatory
  and authored, not derivable; folding them into the derived
  pipeline would make them disappear on the next rebuild and
  would mix two provenance models in one store.
- **Validate after writing (best effort).** Rejected: an
  invalid page would already be on disk, forcing cleanup and
  leaving the bundle in a broken state between write and fix.
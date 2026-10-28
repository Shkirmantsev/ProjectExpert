---
id: modules.llm-wiki
title: LLM Wiki
kind: modules
status: active
summary: The canonical, LLM-curated knowledge layer of a target repository, written through five MCP tools and validated against the OKF v0.2 profile before every store.
sourceRefs:
  - pi_platform/core/wiki/llm_wiki.py
  - pi_platform/mcp/server.py
  - pi_platform/mcp/tool_schemas.py
  - tools/mcp/project-context-mcp/project_context_mcp/server.py
  - tools/mcp/project-context-mcp/project_context_mcp/core.py
maintenance:
  mode: authored
related:
  - adr.0030-llm-wiki-as-curated-knowledge
  - interfaces.mcp-tools
---

# LLM Wiki

The LLM Wiki is the canonical, LLM-curated knowledge layer of a
project. It separates two kinds of knowledge: **derived
knowledge** (parsed, chunked, embedded and rebuilt from the
sources) and **curated knowledge** — pages a calling LLM writes
after it understood the project, explaining *why* the code looks
the way it does, which the parser cannot know. See
[`adr.0030-llm-wiki-as-curated-knowledge`](../adr/0030-llm-wiki-as-curated-knowledge.md).

## Storage

- Implementation: `pi_platform/core/wiki/llm_wiki.py` (`LlmWiki`).
- The Wiki is the Git-versioned OKF v0.2 bundle at
  `project-knowledge/wiki/` of the target repository.
- A curated page is a Markdown file with OKF frontmatter;
  `type` is mandatory and is one of the accepted concept types
  (`Concept`, `Architecture`, `Module`, `Interface`, `Process`,
  `Decision`, `Requirement`, `Glossary`, `Domain`, `Invariant`).
- The reserved `index.md` (navigation) and `log.md` (audit
  trail) are maintained by the platform; they cannot be written
  through the tools.

## MCP surface

The server exposes five tools (registered in
`pi_platform/mcp/server.py`, argument contracts in
`pi_platform/mcp/tool_schemas.py`):

- `project.wiki_list_pages` — list the curated pages (no
  arguments).
- `project.wiki_read_page` — read one page
  (`path`, `include_body` default `true`).
- `project.wiki_search` — search the curated pages by text
  overlap (`query`, `top_k` default `8`).
- `project.wiki_write_page` — create or update a page (`path`,
  `title`, `body`, `type` default `Concept`, `summary`,
  `author` default `calling-llm`, `source`, `dry_run` default
  `false`). No `approval_id`.
- `project.wiki_validate` — validate the bundle against the
  OKF v0.2 profile (no arguments).

## Guarantees

- A write is validated against the OKF v0.2 profile BEFORE it is
  stored; an invalid page is never written.
- The write is atomic (temporary file + `os.replace`) and cannot
  escape the Wiki root (relative-path resolution refuses `..`,
  absolute and home paths).
- Every write is recorded in the reserved `log.md`.
- The navigation section of the reserved `index.md` is refreshed
  after each write.
- A written page becomes part of the searchable corpus on the
  NEXT project refresh; it is not instantly visible through the
  dense index.
- The calling LLM drives the loop: search the project
  (`project.search` / `project.retrieve_context`), read the
  curated pages (`project.wiki_list_pages`,
  `project.wiki_read_page`), write what it learned
  (`project.wiki_write_page`), then `project.wiki_validate`.

## Harness-side counterpart

The harness Wiki (`.ai/wiki/`) keeps its own conventions —
frontmatter `id`, `title`, `kind`, `status`, `summary` — and its
counterpart tool is `kb_write` in
`tools/mcp/project-context-mcp/` (`project_context_mcp/server.py`
+ `core.py`): same atomic, path-safe write contract with the
harness page kinds and statuses, an immediate search-index
refresh, and `python harness.py wiki-validate` as the
consistency gate. The two Wikis stay separate: the LLM Wiki
belongs to the target repository's OKF bundle, the harness Wiki
to this development harness.

## Research enrichment — 2026-10-27

The Wiki is also the place where a dependency research finding
becomes durable, reusable knowledge. The write contract is
extended additively:

- Every page carries a **revision**: the content address of its
  body. `project.wiki_read_page` returns it.
- A write may present the revision it read as `expected_revision`.
  Inside the per-page lock the current revision is compared: a
  changed page produces a **conflict** (with the current revision)
  instead of a silent overwrite. The caller re-reads and merges.
- A write may carry `dependency_notes`: the provenance of the
  research the page explains (package, ecosystem, version, artifact
  hash, evidence references, repository revision, tool version and
  a `fact`/`inference` label). The notes are stored in the
  frontmatter, so a later reader can tell which evidence the text
  is based on.
- `project.wiki_read_page` accepts `inputs`: the current state of
  the dependencies the page explains. The answer then reports the
  recorded evidence that is **stale** (a changed version or a
  changed artifact hash). A stale note does not rewrite the curated
  explanation; it marks it for renewal.
- The write result separates the **stored** state from the
  **indexed** state: `stored`, `index_state` (the navigation index
  of the Wiki) and `retrieval_index_state` (the retrieval index of
  the project, `pending` until the next refresh). The navigation
  refresh is idempotent, so a failed refresh can be retried
  without changing the page.

The curated pages reach the searchable corpus through the existing
retrieval path; no second indexer was added.

## Related

- [`modules.dependency-research`](../modules/dependency-research.md)
- [`interfaces.dependency-research`](../interfaces/dependency-research.md)

## Related

- [`adr.0030-llm-wiki-as-curated-knowledge`](../adr/0030-llm-wiki-as-curated-knowledge.md)
- [`interfaces.mcp-tools`](../interfaces/mcp-tools.md)
- [`modules.mcp-server`](mcp-server.md)
## Review hardening — 2026-10-26

Relative repository roots are normalized. Page and reserved paths reject symlink
components; list/search skip unsafe pages. Atomic writes use unique temporary
files. Mutations are serialized within one process, and audit append failures
are reported even if page storage succeeded. Separate processes are not covered
by that lock.

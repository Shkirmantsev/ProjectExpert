# Design — the LLM Wiki as the curated knowledge layer

## Two kinds of knowledge

| | Derived | Curated |
|---|---|---|
| Source | the repository | a calling LLM |
| Content | what the code does | why the code is this way |
| Lifecycle | rebuilt on every refresh | committed to Git, curated by a human-in-the-loop agent |
| Guarantee | derived from the sources | validated against OKF v0.2, atomic, audited |

The parser cannot produce the second kind. A calling LLM can, once it
has read the project. The platform's job is to give it a safe place to
write and a way to read back.

## Storage contract

`pi_platform/core/wiki/llm_wiki.py` owns the bundle under
`project-knowledge/wiki/`:

* a page is a Markdown file with OKF frontmatter; `type` is mandatory;
* the reserved `index.md` carries `okf_version` and `type: WikiIndex`;
  the reserved `log.md` carries the audit trail;
* a write is rendered with the OKF profile, validated against that
  profile, and only then written — atomically (`.tmp` plus `os.replace`);
* a path that resolves outside the Wiki root is refused;
* the reserved files cannot be overwritten by a page write;
* every write appends one line to the reserved log;
* the navigation section of the reserved index is regenerated.

## The MCP surface

Five tools, all on the target repository:

| Tool | Purpose |
|---|---|
| `project.wiki_list_pages` | the curated pages with their type and summary |
| `project.wiki_read_page` | one page with its frontmatter and body |
| `project.wiki_search` | a text-overlap search over the curated pages |
| `project.wiki_write_page` | create or update a page |
| `project.wiki_validate` | the OKF conformance report |

The write tool does **not** require the operator approval id. That id
guards the derived-knowledge write path (materialisation, refresh),
where the platform writes what it derived. A curated page is what an
agent concluded, written into a bounded, validated, audited location. It
is still bounded: it cannot leave the Wiki root, it cannot break the OKF
profile, and it is recorded.

## Search

A curated page is a Markdown file under the project, so the source
discovery already classifies it as documentation and the pipeline chunks,
embeds and indexes it. The page therefore reaches the corpus and the
next search can use the curated explanation. The Wiki's own text search
exists for the case where the dense index has not been refreshed yet.

## The harness plane

The harness context server owns the harness Wiki convention (stable id,
kind, status, summary). It gains the matching `kb_write` tool so the
framework is complete on both planes: the product MCP curates the
project under test, the harness MCP curates the developing repository.

## Alternatives rejected

* **Generating the pages in the platform.** Rejected: the platform has
  no model of the project's intent; a local model would be both slow and
  weaker than the calling agent. The calling LLM drives the generation.
* **Requiring the approval id for a curated write.** Rejected: it would
  make the curated layer unusable in the agent loop it exists for. The
  safety comes from the validation, the path bound and the audit trail.
* **Storing the curated pages outside the repository.** Rejected: the
  curated knowledge is the durable explanation of the code and belongs
  in Git next to it.

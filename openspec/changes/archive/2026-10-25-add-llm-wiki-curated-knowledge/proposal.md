# Add the LLM Wiki as the curated knowledge layer

## Why

ProjectExpert parses the sources, chunks them, embeds them and indexes
them. That is **derived** knowledge: it is rebuilt from the repository and
it can explain *what* the code does. It cannot explain *why* the code
looks the way it does, because the parser does not know the intent.

The **LLM Wiki** is the second layer: canonical, Git-versioned, curated
knowledge that a CALLING LLM writes after it understood the project. It
is the layer that turns "the code exists" into "the code is this way".

The capability was missing in the product:

* the MCP server could read the project but could not create or read a
  curated page;
* a developing project got an OKF bundle stub but no way to fill it;
* the Wiki was not part of the corpus a search could reach.

The LLM Wiki framework also existed only in the harness repository, as
the tooling that helps developing this project. It must exist in the
developing project itself, so that a project which adopts ProjectExpert
curates its own knowledge.

## What changes

* A new LLM Wiki engine owns the storage contract of the OKF v0.2 bundle
  under `project-knowledge/wiki/`.
* Five MCP tools let a calling LLM curate the knowledge: list the pages,
  read a page, search the pages, write a page and validate the bundle.
* A curated page is validated against the OKF profile BEFORE it is
  stored. An invalid page is never written. The write is atomic, cannot
  escape the Wiki root, and is recorded in the reserved `log.md`.
* The reserved `index.md` keeps its navigation in sync and keeps the
  OKF-required frontmatter.
* A developing project receives the Wiki scaffold when it is initialised.
* A curated page becomes part of the searchable corpus, so the next
  search can use the curated explanation and not only the parsed sources.
* The harness Wiki gains the matching write tool, so the framework is
  complete on both planes.

## Impact

Affects the MCP server surface, the canonical knowledge layout and the
harness context server.

* **Compatibility:** the new tools are additive. The existing §36 tool
  names are unchanged. The curated Wiki is a new directory content; a
  project without curated pages behaves exactly as before.
* **Security:** a curated write is additive knowledge, not derived
  materialisation, so it does not require the operator approval id. It
  is still bounded: path-safe, OKF-validated, audited, and limited to
  the Wiki root of the target repository.
* **Not in scope:** the platform does not generate wiki pages on its own.
  The calling LLM drives the generation; the platform guarantees the
  contract the pages must satisfy.

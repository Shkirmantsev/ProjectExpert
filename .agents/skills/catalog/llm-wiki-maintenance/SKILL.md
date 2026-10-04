---
name: llm-wiki-maintenance
description: Build, update, validate, or repair the Markdown-first project Wiki and its bounded retrieval index without turning generated data into a source of truth.
---

# LLM Wiki maintenance

1. Search/narrow affected knowledge before opening many documents.
2. Treat `.ai/wiki/**/*.md` as canonical explanatory knowledge.
3. Keep `INDEX.md` navigational; place detail in scoped pages.
4. Preserve stable frontmatter IDs across moves.
5. Link to OpenSpec instead of duplicating normative requirements.
6. Separate facts from inference and record evidence paths.
7. Rebuild disposable index with `python harness.py index`.
8. Run `python harness.py wiki-validate` and relevant project tests.
9. Never store secrets, raw transcripts, hidden reasoning, or caches in the Wiki.

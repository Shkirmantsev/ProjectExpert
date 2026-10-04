# Knowledge-area agent rules

`.ai/wiki/` is durable, human-readable project knowledge. Markdown is canonical.

- Use stable frontmatter `id` values. IDs survive file moves.
- Do not store secrets, raw transcripts, hidden reasoning, caches, or generated search indexes in the Wiki.
- Separate fact from inference. Cite repository paths, specs, ADRs, or external source IDs when practical.
- Do not duplicate normative OpenSpec requirements into the Wiki; link and explain them.
- Generated indexes belong under `tmp/local/project-context/` and must be reproducible.
- Keep `.ai/wiki/INDEX.md` navigational and small.

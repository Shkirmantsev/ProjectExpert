# Engineering conventions

These are generic defaults, not universal laws. More specific project/module rules may override them when explicitly documented.

Read only the files relevant to the task:

- [Architecture and design](architecture-and-design.md) — before design or boundary changes.
- [Implementation](implementation.md) — while changing source or configuration.
- [Testing](testing.md) — when selecting regression and integration checks.
- [Interface and feature documentation](interface-and-feature-documentation.md) — when behavior or interfaces change.
- [Verification and quality gates](verification-and-quality-gates.md) — during review and before completion.
- [Generated code](generated-code.md) — when a generator owns the affected output.

The [agent contract](../../AGENTS.md) is the entry point for these defaults.
[OpenSpec rules](../../openspec/config.yaml) connect them to change artifacts.
See the [documentation map](../README.md) and [ownership map](../PROJECT_STRUCTURE.md)
for their relationship to specifications, Wiki knowledge, and runtime configuration.

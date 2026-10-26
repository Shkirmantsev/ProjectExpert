# OKF Profile Reference

The Project Intelligence Platform targets the **Open
Knowledge Format (OKF)** v0.2 profile for the human-readable
Wiki layer. This reference summarises the OKF bundle shape,
the platform-specific extension namespace, the validation
rules the platform applies during materialise, and the
contract for pages a calling LLM curates through
`project.wiki_write_page`.

## Bundle shape

The Git-versioned Wiki is a valid or intentionally profiled
OKF bundle:

```
project-knowledge/
└── wiki/
    ├── index.md
    ├── log.md
    ├── architecture/
    ├── business/
    ├── components/
    ├── dependencies/
    ├── requirements/
    └── specifications/
```

The bundle-root `index.md` declares the targeted OKF
version:

```yaml
---
okf_version: "0.2"
---
```

## Frontmatter

Every non-reserved concept Markdown file carries parseable
YAML frontmatter with a non-empty `type`. Example:

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

## Concept types

OKF only requires a non-empty `type`, but curated pages written
through `project.wiki_write_page` MUST use one of the concept
types the platform accepts (the tool rejects anything else):

`Concept`, `Architecture`, `Module`, `Interface`, `Process`,
`Decision`, `Requirement`, `Glossary`, `Domain`, `Invariant`.

`Concept` is the default when the writer does not choose one.

## Reserved files

The implementation MUST preserve OKF reserved semantics for:

- `index.md` — progressive disclosure and navigation;
- `log.md` — chronological updates for the corresponding
  scope.

## Curated pages written by the calling LLM

A curated page is written by the calling LLM through the MCP
tool `project.wiki_write_page` (arguments and return shape in
`MCP-TOOLS.md`). The write contract is:

- the page is rendered with OKF frontmatter and validated
  against this profile BEFORE it is stored; an invalid page is
  never written;
- the write is atomic and the path is Wiki-relative, so a write
  can never escape the Wiki root;
- every write is appended to the reserved `log.md`, giving the
  curated knowledge an audit trail;
- the navigation section of the reserved `index.md` is
  refreshed; the reserved files themselves cannot be written
  through the tool;
- a written page becomes part of the searchable corpus on the
  next project refresh.

`project.wiki_validate` re-runs the bundle validation on demand
and reports the errors without writing anything.

## Platform extensions

Platform-specific extension fields use the stable `pi_`
prefix. OKF readers ignore unknown metadata; the platform
uses the prefix for richer provenance, lifecycle and version
metadata.

## Out of scope for OKF

These remain derived runtime state, never OKF bundle content:

- dense vectors;
- ANN indexes;
- sparse index internals;
- runtime database pages;
- temporary task context;
- model caches.

## Validation

The materialise pipeline runs OKF validation before any
durable commit:

- parseable YAML frontmatter;
- mandatory `type`;
- valid reserved filenames;
- root declared OKF version when configured;
- stable links where possible;
- platform provenance extensions;
- no accidental runtime / binary files inside the OKF
  bundle.

The CI / release pipeline includes an OKF conformance gate.
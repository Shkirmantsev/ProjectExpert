# OKF Profile Reference

The Project Intelligence Platform targets the **Open
Knowledge Format (OKF)** v0.2 profile for the human-readable
Wiki layer. This reference summarises the OKF bundle shape,
the platform-specific extension namespace and the validation
rules the platform applies during materialise.

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

## Reserved files

The implementation MUST preserve OKF reserved semantics for:

- `index.md` — progressive disclosure and navigation;
- `log.md` — chronological updates for the corresponding
  scope.

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
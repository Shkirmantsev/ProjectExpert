# OKF v0.2 profile descriptor

This directory ships the **OKF v0.2 compatibility profile** that the
Project Intelligence Platform enforces on the Git-versioned Wiki bundle
under `project-knowledge/wiki/`. The image copies this profile and a
**template** only; it never bundles project Wiki content.

| Field | Value |
| --- | --- |
| `profile` | `okf` |
| `profile_version` | `0.2` |
| `compatible_platform_version` | `>=0.8.0 <1.0.0` |
| `reserved_filenames` | `index.md`, `log.md` |
| `mandatory_concept_fields` | `type` |
| `platform_extension_prefix` | `pi_` |

## Contract

`pi_platform.core.canonical.validate_wiki_bundle` enforces this profile
deterministically. The materialisation pipeline runs the validator before
any durable write and leaves the bundle unchanged on rejection (§10.4).

## Template

The `template/` subdirectory contains a minimal conforming bundle. It can
be copied into a fresh project as `project-knowledge/wiki/` to bootstrap a
new repository without authoring any OKF frontmatter by hand:

```text
cp -r distribution/okf-profile/template/* project-knowledge/wiki/
```

The template is itself a valid OKF v0.2 bundle; copying it never produces
an invalid state.

## Anti-goals

This profile does **not** ship:

- project Wiki content;
- dense vectors, ANN indexes or sparse index internals;
- runtime database pages, model caches or temporary task context;
- any third-party OKF revision beyond v0.2.

OKF revisions are translated through `OkfAdapter` (§0.5 Forward
Compatibility); the platform does not couple to a specific OKF minor.
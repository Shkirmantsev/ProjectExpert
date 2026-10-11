# OKF v0.2 template bundle

A minimal conforming OKF v0.2 bundle. Copy it into a fresh project to
bootstrap the canonical Wiki tree:

```text
cp -r distribution/okf-profile/template/* project-knowledge/wiki/
```

## Conformance

The bundle is itself a valid OKF v0.2 bundle, so the copy never produces
an invalid state. To verify after copying:

```bash
python -m pi_platform.cli okf-validate --wiki-root project-knowledge/wiki
```

## Extending

Add concept files under any subdirectory, e.g. `components/`,
`requirements/`, `specifications/`. Every non-reserved Markdown file MUST
declare a non-empty `type` and SHOULD declare `title` plus the
`pi_` extension fields listed in `../PROFILE.md`.
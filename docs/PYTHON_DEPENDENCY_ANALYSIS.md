# Python dependency and library analysis

Production repository discovery indexes `pyproject.toml`, `requirements*.txt`,
`requirements*.in`, `.py`, `.pyi` and `.whl` files through normal project search.
No additional Python parser package is required.

The manifest adapter records project dependencies, optional extras, build-system
requirements and direct dependency-group entries. Records retain normalized
package names, constraints, extras, direct URLs and unevaluated environment
markers. A constraint is never represented as an installed version. Requirement
includes and pip directives are reported but not followed.

Source analysis uses the Python AST for public classes, functions, signatures,
docstrings and imports. Wheel analysis reads METADATA and Python members without
extracting or importing them. An exact wheel version identifies that artifact;
its dependency closure remains unresolved. License metadata is evidence, not
license approval.

## Retrieving third-party library evidence

Obtain a wheel explicitly from your approved package source, then place it in a
non-excluded repository directory such as `dependency-artifacts/`. For example,
run this in your own environment when network retrieval is intended:

```bash
python -m pip download --only-binary=:all: --no-deps --dest dependency-artifacts 'httpx==0.28.1'
```

Start or refresh the production repository index and query `project.search` for
the package, dependency constraint or public API. Downloads are an operator step;
indexing never installs packages, runs setup scripts, imports target modules or
fetches direct URLs. Check redistribution and licensing before storing libraries.
The existing Maven-specific dependency lookup is not a Python resolver.

For isolated inbox processing, put files under `tmp/local/source` and run
`python -m pi_platform.cli ingest-sources --target /path/to/repo`. That command
produces ingestion records; it does not promote inbox files into canonical Wiki
knowledge or automatically add them to the production repository corpus.

## Analysis limits

Dynamic metadata, legacy Poetry declarations, dependency-group includes, lockfile
resolution and transitive dependency resolution are not implemented. Imports do
not prove a distribution mapping. Compiled extension APIs are not extracted;
provide `.pyi` stubs when available. Invalid source syntax or corrupt wheels fail
explicitly. Wheel analysis is bounded to 10,000 entries, 256 MiB expanded data and
5 MiB per analyzed member. Source files are limited to 5 MiB. Analysis uses the
running interpreter's grammar. Unresolved dependencies remain assumptions and
unknown licenses require review.

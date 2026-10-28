# javascript-dependency-intelligence Specification

## Purpose
Describe the JavaScript and TypeScript dependencies of a project from its
manifests, locks and workspaces, and expose the public API of a library
statically. The capability keeps the workspace, scope, alias and
multi-version relationships visible and never implies that a
reconstructed or minified artefact is the original source.

## Requirements

### Requirement: Node dependency and workspace evidence
The platform SHALL inspect package.json, package-lock.json, pnpm-lock.yaml and yarn.lock for documented supported versions, including workspace membership, dev, optional and peer scopes, aliases and multiple installed versions. Unsupported formats and ambiguous peer resolution SHALL be explicit. Analysis SHALL NOT run lifecycle scripts or require whole-tree node_modules indexing.

#### Scenario: Multiple versions and peers
- **GIVEN** a supported lock contains two versions of one package and peer requirements
- **WHEN** research builds the graph
- **THEN** distinct package instances and peer relationships are preserved with evidence

#### Scenario: Workspace origin
- **GIVEN** a monorepo with local workspace links
- **WHEN** the caller requests dependency provenance
- **THEN** local workspace edges differ from registry dependencies and reference bounded repository paths

### Requirement: JavaScript and TypeScript library inspection
The platform SHALL inspect JS, TS, declarations and package exports statically, recording public symbols, signatures where available, imports/reexports and source locations. It SHALL prefer distributed source or local source maps; minified or generated fallback SHALL be labelled and SHALL NOT imply original source recovery. External source-map URLs SHALL NOT be fetched implicitly.

#### Scenario: Mapped dependency code
- **GIVEN** a package archive with JS, declarations and a valid contained source map
- **WHEN** a symbol body is requested
- **THEN** the result uses the best available source with mapping provenance

#### Scenario: Minified library
- **GIVEN** a library without original source or valid maps
- **WHEN** code is requested
- **THEN** a bounded generated or formatted excerpt is labelled accordingly, without fabricated original names

# Dependency research

[Project home](../README.md) · [User guide](USER_GUIDE.md) ·
[Architecture](ARCHITECTURE.md)

Dependency research answers two practical questions: which libraries your
project actually uses, and what the code inside those libraries does. Results
carry their source — which manifest, lock file, installed package or artifact
they came from — so a claim can be checked instead of trusted.

## What is read, per ecosystem

| Ecosystem | What is read | Limits |
|---|---|---|
| Java (Maven/Gradle) | Declared dependencies from `pom.xml` / `build.gradle` | The transitive closure is **not** resolved automatically, because a dependency-tree command executes project code; an explicitly selected local Maven repository supplies installed versions |
| Python | `uv.lock` (lockfile version 1), `poetry.lock` (lock versions 1.1, 2.0, 2.1); `pyproject.toml` and `requirements*.txt` give declared constraints; an explicitly selected environment's dist-info metadata gives installed versions | A declaration is never reported as a resolution |
| Node / JavaScript / TypeScript | `package.json`, `package-lock.json` (npm lockfile versions 1, 2, 3), `pnpm-lock.yaml` (lockfile versions 6.0 and 9.0), `yarn.lock` (Yarn classic v1 and Yarn berry lockfile v2–v8) | Source symbols come from the tree-sitter JavaScript/TypeScript grammars, which are **optional**: without them the Node source evidence is partial and the capability report says so |

Offline inspection is the default. Nothing is downloaded, installed or
executed unless the operator asks for it under the acquisition policy below.

## Research tools over MCP

All four tools are available on the product's MCP endpoint
(`http://localhost:8765/mcp`, Streamable HTTP, POST only):

| Tool | Purpose | Required arguments |
|---|---|---|
| `project.dependency_tree` | Traverse the resolved graph from an ecosystem or package | `ecosystem` (`python`, `java`, `node`); optional `package`, `environment`, `scopes`, `max_depth`, `max_nodes`, `cursor` |
| `project.dependency_search` | Find symbols inside a package | `ecosystem`, `package_ref`, `query`; optional `limit`, `cursor` |
| `project.dependency_read` | Read a bounded excerpt of library code | `evidence_ref` (plus optional `artifact`, `member`, `symbol`, line range, `max_bytes`) |
| `project.dependency_acquire` | Download an exact artifact under the approved-source policy | `ecosystem`, `name`, `version`, `source_id` |

`project.get_dependency` keeps its original Maven argument shape
(`group`, `artifact`, `version`) and now answers from the real dependency
graph rather than a placeholder.

Example question: “Why is this version used, and what does this method do?” —
call `project.dependency_tree` for the version reason, then
`project.dependency_search` and `project.dependency_read` for the method body.

## The same research over A2A

Over A2A the research travels in a versioned envelope with an allowlisted
operation:

```json
{"schema_version": 1, "operation": "dependency.tree", "arguments": {"ecosystem": "java"}}
```

Allowed operations: `dependency.tree`, `dependency.search`, `dependency.read`,
`dependency.acquire`. An unknown operation is rejected; it never succeeds as
an acknowledgement. An unsupported envelope version is rejected the same way.
See the [user guide](USER_GUIDE.md#a2a-for-agent-to-agent-research) for how to
enable and address the A2A surface.

## Artifact acquisition

Acquisition is the only path that fetches bytes from outside the analyzed
repository, and it is deliberately narrow:

- it downloads an exact `name` + `version` from an **approved source only**;
- it verifies the digest of what it received;
- it refuses a redirect that leaves the approved hosts;
- it never runs package code.

It is disabled unless the operator names approved sources with
`PI_RESEARCH_SOURCES` (comma separated, for example `pypi,npm,maven-central`).
Without that setting, every `project.dependency_acquire` call is refused.

## Reading and reconstructed code

Evidence about a library is labelled by how it was obtained:

- extracted source and compiled class files are read as they are;
- a **disassembly is not recovered source** and is labelled as such;
- a **decompilation is a reconstruction**, never the original source;
- **no decompiler is bundled**, so reconstruction is unavailable unless the
  operator provides one;
- **native binaries are never decompiled.**

A citation therefore states whether a reader is looking at original source, a
disassembly or a reconstruction.

## Wiki reuse

Verified findings belong in the curated Wiki so the next session starts with
them instead of repeating the research:

1. `project.wiki_search` — find the topic page that already covers the area.
2. `project.wiki_read_page` — read it, optionally with the current dependency
   state so stale evidence is reported.
3. `project.wiki_write_page` — save the cited finding. Pass the
   `expected_revision` you read: if the page changed meanwhile the write
   returns a **conflict instead of an overwrite**, and `dependency_notes` can
   record the provenance (package, version, artifact hash, evidence
   references, tool version).
4. `project.wiki_validate` — validate the page set.

A page becomes part of the searchable corpus on the **next project refresh**;
until then it is stored but not yet returned by search. Research that records
a dependency state also becomes stale when that state changes, which is what
the `inputs` argument of `project.wiki_read_page` reports.

## Limits worth remembering

- Declarations are not resolutions; absent lock or environment evidence the
  graph reports what it knows and what it does not.
- The optional Node grammars change how complete source evidence is, and the
  capability report says so when they are missing.
- Acquisition needs an explicit operator policy and never executes what it
  downloads.
- Reconstruction is labelled, and native binaries stay untouched.

## Related pages

- [README](../README.md) — quick start and capability matrix.
- [User guide](USER_GUIDE.md) — connecting tools and first queries.
- [Architecture](ARCHITECTURE.md) — where research fits in the data process.
- [Configuration](CONFIGURATION.md) — settings and precedence.
- [Production install](PRODUCTION_INSTALL.md) — installation and upgrades.
- [Troubleshooting](TROUBLESHOOTING.md) — missing evidence and readiness.
---
id: modules.dependency-research
title: Dependency research service
kind: modules
status: active
summary: The shared, language-neutral service that answers dependency questions with bounded, evidence-backed graphs, symbols and code for Java, Python and Node.
---

# Dependency research service

The dependency research service answers questions about the
libraries a project uses. It is **one** service: the MCP tools, the
A2A adapter and the CLI all call it, so an answer does not change
when it travels through a different transport.

- Port: `pi_platform/ports/research/dependency_research.py`
  (`DependencyResearchPort`) and
  `pi_platform/ports/research/ecosystem.py`
  (`EcosystemResearchPort`).
- Domain records, policy, graph and service:
  `pi_platform/core/research/{records,policy,graph,service}.py`.
- Adapters: `pi_platform/adapters/research/`.

## The record contract

| Record | Meaning |
|---|---|
| `Package` | ecosystem, normalized name, declared constraint, optional resolved version, scope, source kind, environment. A `None` resolved version means *unknown*; a constraint is not a resolution. |
| `PackageInstance` | a package identity plus the context that makes it unique: lock location, workspace, peer context and alias. Two versions of one package stay distinct. |
| `DependencyEdge` | source, optional target, dependency kind, marker/extra/peer condition and the evidence reference. An unresolved target is allowed. |
| `EvidenceReference` | repository identity/revision, artifact hash, contained member, lines, parser version, representation kind and license/access policy. |
| `ResearchResult` | schema version, snapshot id, status, completeness, nodes/edges, excerpts, warnings, evidence, truncation, cursor, effective limits and scope. |

`status` is `complete`, `partial`, `unavailable`, `denied`,
`unsupported` or `failed`. `completeness` is relative to the
*requested* environment and scope; it never claims that every extra
or platform was considered. A partial graph and a failed call are
never conflated.

## Limits and cursors

`ResearchLimits` carries the default limits (100 graph nodes, depth
5, 20 symbol hits, 200 lines or 16 KiB of code, 30 s per call) and
the hard maxima (1 000 nodes, depth 20, 200 hits, 1 000 lines or
64 KiB, 120 s). A negative or unbounded request is rejected; a
request above a hard maximum is clamped and the *effective* limits
are reported in the result.

A cursor is bound to the snapshot, the query, the policy and the
project. A cursor from another snapshot, another query, another
policy or another project is rejected as stale instead of
continuing the wrong traversal.

## The ecosystem adapters

| Ecosystem | Offline evidence | Boundary |
|---|---|---|
| Python | `uv.lock` (lockfile version 1), `poetry.lock` (1.1, 2.0, 2.1), `pyproject.toml`, `requirements*.txt`, and the installed metadata of an **explicitly selected** environment root | No import, no install, no network. A marker, extra or group is preserved, never evaluated against the host. |
| Java | `pom.xml`, `build.gradle(.kts)` declarations and the installed versions of an **explicitly selected** local repository | A dependency-tree command executes project code, so the transitive closure is not resolved by a research call. |
| Node | `package.json`, `package-lock.json` (npm 1-3), `pnpm-lock.yaml` (6.0, 9.0), `yarn.lock` (classic v1, berry v2-v8) and the workspace source symbols | The static parser (tree-sitter with the JavaScript/TypeScript grammars) is **optional**; without it the Node source evidence is partial and the capability report says so. |

An unknown lock version is rejected with an actionable diagnostic.
A guessed dependency graph is worse than an explicit "not
supported".

## Acquisition and reconstructed code

Inspection never touches the network and never runs dependency
code. Acquisition is an explicit, policy-controlled operation: an
approved source identity, an exact name and version, a redirect
that stays on the approved hosts, a digest that must match, a
bounded size and time, and an atomic publication that never
leaves a partial artifact behind. The cache is content addressed
and idempotent.

The representations are distinct on purpose: `source`, `stub`,
`generated`, `mapped-source`, `disassembly` and `decompiled`. A
disassembly is not recovered source. No decompiler is bundled and
native binaries are never decompiled. The optional Java decompiler receives
a read-only input copy in a disposable directory; cleanup also clears the
Windows read-only attribute. Its invocation test uses the current Python
interpreter as a portable stub, without requiring a shell or a bundled
decompiler. See
[`adr.0031-cross-language-research-tooling-policy`](../adr/0031-cross-language-research-tooling-policy.md).

## What the service does not do

- It does not resolve a Java closure by running a build tool.
- It does not import a Python package or install anything.
- It does not ingest `node_modules`, `.venv` or binaries into the
  general source discovery.
- It does not return a placeholder for a capability it lacks: an
  unsupported ecosystem, an unknown lock format and a missing
  parser are reported as such.

## Related

- [`interfaces.dependency-research`](../interfaces/dependency-research.md)
- [`modules.llm-wiki`](../modules/llm-wiki.md)
- `docs/DEPENDENCY_RESEARCH.md`

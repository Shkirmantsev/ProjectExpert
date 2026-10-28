---
id: adr.0031-cross-language-research-tooling-policy
title: ADR 0031: Cross-language research tooling policy
kind: adr
status: active
summary: The optional-parser and decompiler policy for dependency research: one MIT static parser, no bundled decompiler, labelled reconstructions and policy-controlled acquisition.
---

# ADR 0031: Cross-language research tooling policy

- Status: accepted
- Date: 2026-10-27
- Deciders: implementation of `improve-dependency-research-and-onboarding`

## Context

The dependency research service reads dependency code. Reading
*source* is safe; reading *compiled* code needs a tool, and a tool
is a supply-chain decision: it runs code from an untrusted
ecosystem on the host, it has a licence, it has versions it
supports, and it can be absent.

The design forbids a false capability: a tool that is missing must
not produce an invented answer, and a reconstructed body must never
be presented as the original source.

## Decision

1. **One static parser, optional, MIT.** Node source analysis uses
   `tree-sitter` with the `tree-sitter-javascript` and
   `tree-sitter-typescript` grammars (all MIT). They are declared
   as the optional `node` extra and are **not** part of the
   `production` extra: the core harness and the production image
   stay unchanged, and a deployment without them reports partial Node
   evidence and a capability diagnostic. A regular expression is
   never substituted for a real ESM/CJS/TypeScript parse.

2. **No bundled decompiler.** A Java decompiler is an operator
   choice. The service accepts an explicitly allowlisted executable
   and invokes it with a fixed argument vector, a read-only input, a
   disposable work directory, no network, a bounded output and a
   bounded runtime. Without an allowlisted tool the capability is
   reported as unavailable and a class file is read as a
   **signature** only.

3. **Bytecode is a disassembly, not source.** Python `.pyc` files
   are read with the standard library `dis` module. The result is
   labelled `disassembly`. A `.pyc` whose magic number does not
   match the running interpreter is reported as an unsupported
   version, never guessed.

4. **Native binaries are never decompiled.** There is no supported,
   bounded reconstruction for `.so`, `.pyd`, `.dylib`, `.node`,
   `.dll` or `.exe`; the service refuses them explicitly.

5. **Acquisition is policy-controlled and separate from
   inspection.** An artifact is downloaded only for an approved
   source identity and an exact name and version, the redirect must
   stay on the approved hosts, the digest must match, the size and
   the time are bounded, and a failed download publishes nothing.
   The cache is content addressed and idempotent.

6. **Every reconstruction is labelled.** The representations
   `source`, `stub`, `generated`, `mapped-source`, `disassembly` and
   `decompiled` are distinct in the result and in the Wiki
   provenance.

## Consequences

- The production image and the `production` extra do not grow.
- A deployment that wants Node source symbols installs the `node`
  extra and gets a capability report that says the parser is
  available.
- A deployment that wants decompiled Java bodies supplies and
  allowlists a tool; the service never downloads one.
- The licence evidence for the optional grammars is recorded in
  `distribution/licenses/` and in the dependency inventory.

## Related

- [`modules.dependency-research`](../modules/dependency-research.md)
- [`adr.0029-portable-model-runtime-and-oci-kit`](0029-portable-model-runtime-and-oci-kit.md)
- [`adr.0030-llm-wiki-as-curated-knowledge`](0030-llm-wiki-as-curated-knowledge.md)

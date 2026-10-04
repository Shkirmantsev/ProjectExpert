# local-source-inbox Specification delta

Covers architecture section §9 (Local Dynamic Source Inbox),
specifically §9.2 (Source Promotion Policy). Defines the
`LocalSourceInboxScanner` that walks `tmp/local/source/**`, applies
the documented `LOCAL_ONLY` / `REFERENCE` / `SNAPSHOT` policies and
hands the discovered sources to the `SourceAdapterRegistry` for
ingestion.

The Phase 1 `project-knowledge-repository-layout` capability defines
the on-disk layout (`tmp/local/source/` is Git-ignored by default);
the Phase 1 `git-version-aware-runtime` capability provides the
working-tree overlay that the scanner consults to skip files already
covered by Git-versioned knowledge; the `content-addressed-processing`
capability provides the SHA-256 cache key so unchanged sources are
not re-ingested.

## ADDED Requirements

### Requirement: LocalSourceInboxScanner

The platform MUST expose a `LocalSourceInboxScanner` that recursively
walks `tmp/local/source/` (configurable via
`project-context.yaml:sources.localInbox.path`) and yields a
`Source` value type per file. The scanner MUST:

- honour the per-source promotion policy declared in
  `project-context.yaml:sources.localInbox.policies` (a
  path-glob → policy map; the default policy is `LOCAL_ONLY`);
- compute the SHA-256 hex digest of each file's deterministic byte
  stream as the `Source.contentHash`;
- skip files whose SHA-256 is already present in the runtime cache
  for the active `ProjectVersion` (cache reuse per
  `content-addressed-processing`);
- skip files that are still tracked by Git (the working-tree overlay
  from the Phase 1 Git module flags a path as Git-tracked when the
  path exists in HEAD and the index; such paths are NOT eligible for
  inbox ingestion because the canonical knowledge already covers
  them);
- skip files whose size exceeds the documented per-source byte limit
  (default 256 MiB; configurable) and record an operational log
  warning naming the path, the size and the limit;
- yield sources in a deterministic order (sorted ascending by
  relative path string) so two scanner runs over the same inbox
  produce byte-identical `Source` lists.

#### Scenario: scanner walks tmp/local/source recursively

Given an inbox containing
`tmp/local/source/requirements/r1.md`,
`tmp/local/source/customer/c1.pdf` and an empty subdirectory
`tmp/local/source/diagrams/`
When the scanner is invoked with the default `LOCAL_ONLY` policy
Then the scanner yields exactly two `Source` records (one per file,
in the deterministic path order)
And the empty subdirectory does not produce a source
And every emitted source carries the SHA-256 hex digest of the file
contents in `Source.contentHash`.

#### Scenario: scanner skips Git-tracked files

Given an inbox containing `tmp/local/source/extra.md` and a target
project whose Git index already contains `extra.md`
When the scanner is invoked
Then the scanner does not yield a source for `extra.md`
And the scanner records an operational log entry naming the path
and the reason (`git-tracked`).

### Requirement: SourcePromotionPolicy

The platform MUST expose a `SourcePromotionPolicy` enum with the
documented values:

- `LOCAL_ONLY` — parse and index locally; never commit the source
  bytes or a canonical snapshot. The runtime cache carries the
  derived chunks; the canonical tree carries the provenance and
  metadata only;
- `REFERENCE` — parse and index locally; persist only the provenance
  / reference metadata. The runtime cache carries the chunks with a
  `KnowledgeState.ASSUMPTION` flag naming the source path;
- `SNAPSHOT` — parse and index locally; normalise the source into an
  approved canonical representation and copy it into the canonical
  Git tree under `project-knowledge/sources/`. The runtime cache
  carries the chunks with `KnowledgeState.VERIFIED` and the canonical
  tree holds the snapshot bytes plus the resulting entities.

The scanner MUST record the policy in `Source.metadata` so downstream
stages (chunking, enrichment, graph emission) can branch on the policy
without re-reading `project-context.yaml`.

#### Scenario: LOCAL_ONLY source is not materialised

Given a `Source` whose `SourcePromotionPolicy` is `LOCAL_ONLY`
When the scanner emits the source
Then `Source.metadata.policy = "LOCAL_ONLY"`
And the driver marks the resulting chunks with
`KnowledgeState.UNKNOWN` provenance pointing at the source path
And the canonical materialise step refuses to copy the source bytes
into `project-knowledge/sources/`.

#### Scenario: REFERENCE source persists metadata only

Given a `Source` whose `SourcePromotionPolicy` is `REFERENCE`
When the scanner emits the source
Then the resulting chunks carry `KnowledgeState.ASSUMPTION` with
the rationale naming the source path
And the canonical materialise step writes a single
`SourceReference` metadata record to `project-knowledge/sources/`
without copying the source bytes.

#### Scenario: SNAPSHOT source normalises to canonical tree

Given a `Source` whose `SourcePromotionPolicy` is `SNAPSHOT` and the
operator approves the materialise step
When the materialise step runs
Then the canonical tree holds a normalised copy of the source under
`project-knowledge/sources/<source-id>/`
And the resulting chunks carry `KnowledgeState.VERIFIED` provenance
with the canonical bytes' SHA-256 hex digest as `Evidence.sourceHash`.

### Requirement: per-policy path overrides

The scanner MUST honour per-path overrides declared in
`project-context.yaml:sources.localInbox.policies` so an operator can
override the default policy for a specific path glob. The override
MUST take precedence over the default policy and MUST be applied
deterministically (the longest matching glob wins; ties broken by
sort ascending by glob string).

#### Scenario: per-path override takes precedence

Given a default policy of `LOCAL_ONLY` and an override glob
`customer/**` mapped to `SNAPSHOT`
When the scanner is invoked
Then files under `tmp/local/source/customer/**` are emitted with
`policy="SNAPSHOT"`
And files elsewhere are emitted with `policy="LOCAL_ONLY"`.

### Requirement: deleted-file invalidation

The scanner MUST observe `Source` deletions between two runs and
record the previously derived chunks as `KnowledgeState.STALE` so
the Phase 3 freshness tracker (`KnowledgeState`) flags them for the
next materialise. The scanner MUST NOT delete the canonical
snapshot when the source was a `SNAPSHOT` source; the canonical
snapshot lives under `project-knowledge/sources/` and is removed only
by an explicit operator action.

#### Scenario: deleted source marks derived chunks stale

Given a previous scanner run that emitted `Source` `s-1` with three
chunks in the runtime cache
And the file `tmp/local/source/r1.md` has been deleted before the
next run
When the scanner is invoked again
Then the scanner records `s-1` as deleted
And the three derived chunks transition to `KnowledgeState.STALE`
in the runtime cache
And the operational log records the transition.

## Phase 2 task coverage

The change lists Phase 2 tasks 49 (local source inbox scanner) and
56 (`local-source-inbox` spec scenarios), plus the local-inbox
portion of task 59 (focused regression tests).

Out of scope:

- the Confluence and intranet adapters listed in §3 — those land as
  later Phase 2+ capabilities behind the `SourceAdapter` port;
- the runtime DB schema for the inbox cache (Phase 3 task 62);
- the policy engine that may one day gate the policies (Phase 7 task
  98). The Phase 2 scanner uses the static per-path map; the Phase 7
  policy engine may later consult the same map for higher-level
  decisions.
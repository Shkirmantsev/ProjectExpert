# 2026-10-04-metadata-filters Specification

## Purpose
TBD - created by archiving change implement-phase-4-retrieval. Update Purpose after archive.
## Requirements
### Requirement: MetadataFilter contract

The platform MUST expose a `MetadataFilter` value type in
`pi_platform/ports/retrieval/metadata_filter.py` with the
following fields:

- `queryDate: Optional[date]` — temporal reference date; when
  `None`, the filter uses `today`;
- `projectVersion: Optional[VersionIdentity]` — bind to a specific
  project / Git version;
- `languages: Optional[Sequence[str]]` — restrict results to one or
  more document languages;
- `businessDomains: Optional[Sequence[str]]` — restrict results to
  one or more business domains;
- `modules: Optional[Sequence[str]]` — restrict results to one or
  more modules;
- `requirementIds: Optional[Sequence[str]]` — restrict results to
  one or more requirement identifiers;
- `securityClassifications: Optional[Sequence[str]]` — restrict
  results to documents whose security classification is in the
  allow-list (per §56 enterprise security boundary).

The platform MUST expose a `MetadataFilterPort` abstract class with:

- `apply(filter: MetadataFilter, hits: Sequence[RetrievalHit]) ->
  Sequence[RetrievalHit]` — drop hits whose metadata violates the
  filter;
- `validate(filter: MetadataFilter) -> Sequence[str]` — return the
  list of validation issues (empty list when the filter is
  well-formed).

#### Scenario: filter narrows the candidate set

Given a candidate set that contains hits from German and English
chunks
When `apply(MetadataFilter(languages=["en"]), hits)` runs
Then only the English hits remain
And `stats()` records the dropped-hit count.

### Requirement: temporal validity projection

The `MetadataFilter.apply` operation MUST enforce the §24 rule
`validFrom <= queryDate AND (validTo IS NULL OR validTo >=
queryDate)` on every hit whose metadata carries `validFrom` /
`validTo` fields. Hits whose metadata lacks the temporal fields
MUST be treated as always-valid and MUST NOT be silently dropped.

#### Scenario: temporal validity drops stale hits

Given a chunk with `validFrom="2026-01-01"` and
`validTo="2026-06-30"`
When `apply(MetadataFilter(queryDate=date(2026, 9, 1)), hits)`
runs
Then the chunk is dropped
And the drop reason is `temporal_invalid`.

#### Scenario: temporal validity keeps open-ended hits

Given a chunk with `validFrom="2026-01-01"` and `validTo=None`
When `apply(MetadataFilter(queryDate=date(2026, 9, 1)), hits)`
runs
Then the chunk is kept.

#### Scenario: always-valid chunks survive temporal filtering

Given a chunk with no `validFrom` / `validTo` fields
When `apply(MetadataFilter(queryDate=date(2026, 9, 1)), hits)`
runs
Then the chunk is kept
And the drop reason is `none`.

### Requirement: project-version filter

The `MetadataFilter.apply` operation MUST honour
`projectVersion` so the multi-stage pipeline can restrict results to
the bound Git commit / branch. The phase 4 `git-version-aware-runtime`
capability provides the `VersionIdentity` that the filter consumes.

#### Scenario: project-version filter restricts to one branch

Given a candidate set that contains hits from branches `A` and `B`
when the runtime is bound to `branch="A"`
And `apply(MetadataFilter(projectVersion=VersionIdentity(gitHead=
"abc", ...)), hits)` runs
Then only hits from branch `A` remain
And hits from branch `B` are dropped with reason
`version_mismatch`.

### Requirement: security classification filter

The `MetadataFilter.apply` operation MUST honour
`securityClassifications` per the §56 enterprise security boundary.
Hits whose security classification is not in the allow-list MUST
be dropped with reason `security_denied`. The platform MUST never
return a security-denied hit even when the agent is otherwise
authorised.

#### Scenario: security allow-list drops denied classifications

Given a candidate set that contains hits with classifications
`PUBLIC`, `INTERNAL` and `RESTRICTED`
When `apply(MetadataFilter(securityClassifications=["PUBLIC",
"INTERNAL"]), hits)` runs
Then only the `PUBLIC` and `INTERNAL` hits remain
And `RESTRICTED` hits are dropped with reason `security_denied`.

#### Scenario: empty security allow-list drops every hit

Given an agent without any security clearance
When `apply(MetadataFilter(securityClassifications=[]), hits)`
runs
Then the returned list is empty
And every dropped hit carries reason `security_denied`.

### Requirement: filter ordering is deterministic

The `MetadataFilter.apply` operation MUST drop hits in the order
`temporal_invalid`, `version_mismatch`, `security_denied`,
`language_mismatch`, `domain_mismatch`, `module_mismatch`,
`requirement_mismatch`. The drop reasons MUST appear in the
returned `RetrievalHit.dropReason` field so the multi-stage
pipeline can report the breakdown.

#### Scenario: drop reasons are recorded

Given a candidate set with one chunk per drop reason
When `apply(MetadataFilter(queryDate=date(2026, 9, 1),
projectVersion=...), hits)` runs
Then every returned hit carries a `dropReason` field that is one
of the documented reasons
And the ordering matches the documented priority.


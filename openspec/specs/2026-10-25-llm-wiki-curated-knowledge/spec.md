# llm-wiki-curated-knowledge Specification

## Purpose

Define the canonical, curated knowledge layer of a project: the OKF bundle a
CALLING LLM writes after it understood the project, and the contract the
platform enforces on those pages.

This capability separates curated knowledge from derived knowledge. Derived
knowledge is parsed from the sources and rebuilt on every refresh. Curated
knowledge explains WHY the code looks the way it does, cannot be derived by a
parser, and is therefore written by an agent that read the project. The
platform guarantees the contract the pages must satisfy: OKF conformance
before storage, an atomic and path-bound write, an audit trail, and
discoverability by the search.

## Requirements

### Requirement: LLM Wiki tools

The MCP server MUST expose tools that let a calling LLM curate the
canonical project knowledge: list the curated pages, read one page,
search the pages, write a page and validate the bundle.

The tools MUST operate on the OKF bundle of the target repository. The
write tool MUST accept the page path, the title, the Markdown body, the
OKF concept type, an optional summary, the author and the source of the
page, and a dry-run flag.

A curated page MUST be validated against the OKF profile BEFORE it is
stored. An invalid page MUST NOT be written. The write MUST be atomic,
MUST NOT escape the Wiki root, and MUST be recorded in the reserved log
of the bundle. The reserved index MUST keep its OKF frontmatter and its
navigation MUST stay in sync with the pages.

A curated write MUST NOT require the operator approval id: it is
additive curated knowledge, not derived materialisation. The derived
write tools MUST continue to require it.

#### Scenario: a calling LLM writes and reads a page

Given a target repository with an initialised Wiki
When the caller writes a page and then reads it
Then the read returns the page the caller wrote
And the bundle still satisfies the OKF profile
And the reserved log records the write

#### Scenario: an invalid page is never stored

Given a target repository with an initialised Wiki
When the caller writes a page with an unknown concept type
Then the write is refused with an actionable error
And the page is not stored

#### Scenario: a page cannot escape the Wiki root

Given a target repository with an initialised Wiki
When the caller writes a page outside the Wiki root
Then the write is refused with an actionable error
And nothing outside the Wiki root is written

#### Scenario: a dry run stores nothing

Given a target repository with an initialised Wiki
When the caller writes a page with the dry-run flag
Then the write reports what it would do
And no file is written

#### Scenario: the bundle can be validated on demand

Given a target repository with a Wiki bundle
When the caller asks for the bundle validation
Then the report states whether the bundle satisfies the OKF profile
And the report lists every violation

### Requirement: a developing project owns its LLM Wiki

A project that is initialised MUST receive the Wiki scaffold: the
reserved index with the OKF-required frontmatter and the reserved log.
The scaffold MUST NOT overwrite an existing curated page.

A curated page MUST be part of the searchable corpus, so a search can
reach the curated explanation and not only the parsed sources.

#### Scenario: an initialised project has a usable Wiki

Given a fresh target repository
When the project is initialised
Then the Wiki bundle exists with the reserved index and the reserved log
And the bundle satisfies the OKF profile

#### Scenario: a curated page is searchable

Given a project with a curated Wiki page
When the project corpus is collected
Then the curated page is a retrieval candidate

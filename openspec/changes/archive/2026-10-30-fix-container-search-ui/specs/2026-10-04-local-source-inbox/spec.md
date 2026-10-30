## ADDED Requirements

### Requirement: Automatic runtime inbox inclusion
Automatic indexing and source-version monitoring SHALL include the configured local inbox recursively, even when Git ignores it, using its scanner size limit and policy. The default remains tmp/local/source. Other tmp/local runtime artifacts SHALL remain excluded. Paths outside the target and symlinked trees SHALL be rejected or skipped. Inbox chunks SHALL retain promotion policy and SHALL NOT automatically become canonical Wiki pages.

#### Scenario: Local PDF and nested notes
Given ignored PDF and Markdown files in tmp/local/source and unrelated cache files in tmp/local
When indexing runs
Then the inbox documents are parsed by their supported adapters, searchable with LOCAL_ONLY provenance and visible in sources; unrelated cache files remain excluded.

#### Scenario: Inbox changes invalidate the generation
Given an indexed inbox file
When it is edited or removed
Then source-version monitoring changes and the next generation updates or removes its evidence.

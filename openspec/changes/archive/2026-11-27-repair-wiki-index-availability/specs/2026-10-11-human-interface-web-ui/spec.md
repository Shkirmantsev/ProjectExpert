## ADDED Requirements

### Requirement: Independent browser search, chat and export feedback

The primary Search action SHALL request local excerpts. A configured chat provider SHALL be invoked only by an explicit answer request from an authorised browser. Unavailable index-backed searches SHALL explain how to check index readiness. Ready status SHALL show indexed source coverage and the count of indexed curated pages.

An explicit local index update SHALL report the outcome of automatic Git export separately from index success. A successful export SHALL identify the generated snapshot manifest and whether vectors were included. The UI SHALL explain that the operator commits generated files separately. An expired automatic approval SHALL report how to renew it and SHALL avoid generating a new proposal.

#### Scenario: Search while the first index is being built
Given the application is serving its UI and no consistent index is published
When the reader searches project excerpts
Then the UI indicates that search is unavailable and directs the reader to index status.

#### Scenario: Local index update with automatic Git export enabled
Given an authorised operator has enabled automatic Git export
When the update finishes
Then the UI reports the export outcome and whether files changed, independently of index success.

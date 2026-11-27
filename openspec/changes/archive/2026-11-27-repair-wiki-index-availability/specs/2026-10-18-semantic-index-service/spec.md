## ADDED Requirements

### Requirement: Stable index identity across sharing preferences

Repository indexing SHALL use repository-relative portable identities across both indexing engines, independently of sharing preferences. Private text inbox citations SHALL retain their native paths in search results. A change to sharing preferences SHALL preserve compatible parse results and vectors. Older records with different identities may be rebuilt once on upgrade.

#### Scenario: Enable sharing after the first local index
Given a resumable local index and unchanged project files
When the operator enables Git export and updates the index
Then the platform reuses the existing parsed outputs and vectors
And publishing continues to require the applicable safety and approval checks.

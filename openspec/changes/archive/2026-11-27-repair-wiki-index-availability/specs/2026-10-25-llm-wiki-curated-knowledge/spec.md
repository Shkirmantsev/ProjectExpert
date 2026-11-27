## ADDED Requirements

### Requirement: Curated Wiki browser availability

The authorised browser Wiki operation SHALL search the confined authored Wiki bundle by keyword overlap independently of semantic index readiness. It SHALL respect managed workspace import state. The subsequent index refresh SHALL include new or changed curated pages and reuse compatible parsed outputs and vectors of unchanged sources.

#### Scenario: Browse a newly written page during indexing
Given a curated Wiki page has been stored and the workspace is available
When a reader searches matching keywords while the semantic index is building
Then the matching Wiki page is returned without waiting for the semantic index.

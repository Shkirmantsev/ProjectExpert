## ADDED Requirements

### Requirement: Exact production closure acceptance
The release gate MUST accept an operator-reviewed dependency coordinate only
when its name, version and license expression match a review bound to the exact
lock, inventory and retained evidence hashes. The review MUST identify the
accepting operator, date, decision and obligations. Default policy MUST remain
unchanged, and accepted coordinates MUST appear in release NOTICE and SBOM.

#### Scenario: Changed closure invalidates acceptance
Given an approved production dependency review
When the lock, inventory or retained evidence bytes change
Then release fails until the changed closure is reviewed again.

#### Scenario: Proposed review remains blocked
Given a review with proposed status or a pending coordinate decision
When a production build or publication runs
Then the license gate refuses release.

## ADDED Requirements

### Requirement: Generated SBOM exclusion
Default discovery SHALL exclude generated distribution/sbom output from source
identity while preserving other distribution source documents.

#### Scenario: SBOM rewritten during indexing
- **WHEN** generated SBOM timestamps change without a source edit
- **THEN** the content version remains unchanged

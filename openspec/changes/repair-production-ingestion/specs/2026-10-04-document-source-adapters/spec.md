## ADDED Requirements

### Requirement: reviewed legacy source decoding
The platform MUST decode Java, SQL and plain text using strict Unicode precedence and reviewed repository-relative legacy fallback rules, without modifying source bytes or guessing language encodings. Conflicting matching rules MUST be rejected.

#### Scenario: multilingual legacy source
- **WHEN** an operator configures a compatible CP1252, CP1251 or Japanese legacy rule
- **THEN** source text is decoded losslessly and records contain decoding provenance
- **AND** original file bytes remain unchanged

#### Scenario: independent compatibility
- **WHEN** a fallback rule changes for one source
- **THEN** its pipeline identity changes and unrelated sources retain compatible cache keys
- **AND** portable imports cannot silently reuse the incompatible source

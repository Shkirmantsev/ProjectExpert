## ADDED Requirements

### Requirement: Safe Wiki filesystem operations
Wiki operations SHALL normalize relative repository roots, reject symlink components in page and reserved paths, and use unique temporary files for atomic replacement. An audit append failure SHALL be reported even when page storage succeeded.

#### Scenario: Reserved log points outside the Wiki
- **GIVEN** a symlink at the reserved audit log
- **WHEN** a page write is requested
- **THEN** it fails before storing the page or modifying the symlink target

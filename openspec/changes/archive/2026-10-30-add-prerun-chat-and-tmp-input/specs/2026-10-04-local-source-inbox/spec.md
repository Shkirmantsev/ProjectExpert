## ADDED Requirements

### Requirement: Target tmp document input
The target project's tmp directory SHALL also provide recursively discovered local document inputs with LOCAL_ONLY policy and the configured inbox document byte limit. Existing tmp/local/source support SHALL remain. Runtime tmp/local scratch outside a source inbox, cache/build/vendor trees, unsupported formats and symlink escapes SHALL remain excluded. Hydration SHALL add /tmp/ to local Git exclusions without untracking existing files. Eligible document edits and removals SHALL affect version identity and the next search generation.

#### Scenario: Large private PDF in nested tmp
Given an untracked PDF larger than the repository scan limit but below the local document limit in tmp/reports/nested
When automatic discovery runs
Then it is an eligible LOCAL_ONLY source despite Git ignoring tmp and without ingesting runtime scratch caches.

#### Scenario: Existing tracked temporary source
Given a tmp file already tracked by Git
When source discovery runs
Then it remains eligible under normal repository rules and is not reclassified as an untracked private inbox file.

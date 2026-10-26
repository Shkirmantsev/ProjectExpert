## Why
Python manifests and libraries currently become plain text, while Java dependencies have structured evidence. Recent embedding migration also left release gates using retired model contracts.

## What Changes
Add static Python manifest, wheel metadata and public source API ingestion through the existing pipeline. Preserve dependency specifiers, extras, markers and source evidence without executing project code or installing packages. Fix confirmed Wiki path handling and portable deployment/release regressions.

## Impact
Additive source families, searchable dependency/API records, no new runtime dependencies. Existing Java behavior remains supported. Hardware acceptance is limited to available hosts.

# Pre-run chat binding and private tmp sources

## Why
Operators need to bind optional LLM settings before starting the HTTP server and optionally do so through platform-start. The previous tmp/local/source fix did not give arbitrary target tmp documents the same large-document limit, LOCAL_ONLY metadata or Git exclusion.

## What changes
Add a container CLI chat configuration group, Make configure/status/test/disable commands and opt-in LLM=1/0 startup dependency. Scan target tmp recursively as private inputs, preserving runtime scratch/cache exclusions and the existing configurable inbox.

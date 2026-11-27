# Repair Wiki, search and export feedback

## Why

The first index build made semantic search and the independent Wiki browser
return the same 503. Index progress omitted the Wiki page count. The update
result omitted the outcome of automatic Git export. Enabling export could
invalidate the existing index keys and rebuild every vector.

## What Changes

Let the browser read saved Wiki pages during indexing. Keep primary Search
local and make chat generation explicit. Display Wiki coverage and Git export
outcomes. Keep source identities stable across sharing settings.

Affected capabilities are the web UI, curated LLM Wiki, and semantic indexing.

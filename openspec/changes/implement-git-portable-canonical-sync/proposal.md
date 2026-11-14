# Git-portable production canonical snapshots

## Why
The supplied 2026-11-14 design describes disconnected v1 materialisation and
resumable production state. Current branch is feature/generate-init-project at
af632b4544e620373ad5dd32013d1c68a21897da. The supplied baseline is historical;
implementation uses this branch, as explicitly requested, without switching dev.

## What changes
Add opt-in production snapshot proposals and signed root-last publication,
verified bounded v2 JSONL, pre-parse source-cache import, optional textual vectors,
generated-output exclusions, and truthful legacy hydration. Retain v1, local
SQLite recovery, default indexing and offline deployment behavior.

## Compatibility
Portable identity is opt-in: existing unconfigured source caches retain their
original keys. Enabling portable identity intentionally invalidates old absolute
path keys once. No existing SQLite schema or files are removed. Physical Windows,
Docker offline assets and million-record performance require separate evidence.

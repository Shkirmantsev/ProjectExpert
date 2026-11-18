# Repair production ingestion

## Why
Windows production reports strict UTF-8 decoding failures for legacy Java/SQL, duplicate generated worktrees, repeated failed jobs, slow stop and generic asset errors. Current code confirms these mechanisms; hardware/asset root cause is unknown.

## Changes
Add reviewed path-scoped strict decoding with per-source compatibility identity; prune generated Claude worktrees at Python/Go boundaries; suppress unchanged permanent failures with explicit retry; quiesce before backup; improve offline diagnostics and truthful readiness documentation.

## Limits
Keep current branch and local commits only. Never rewrite sources, relax completeness, publish protected data, bypass hashes, download models, delete locks/volumes or alter this Linux live installation. Physical Windows corpus/GPU/PDF acceptance remains external.

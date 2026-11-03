# Repair portable deployment runtime

## Why
The deployed kit uses 1024-token embedding batches, smaller than observed 1049-token inputs. It exports no Open WebUI service and has no explicit managed-template upgrade, encouraging edits that are lost on re-export. Claims of permanently sticky readiness require regression proof rather than deleting runtime settings.

## What changes
Use 4096-token context, batch and microbatch defaults for native and container launch paths. Ship an optional, loopback-bound Open WebUI profile connected to the ProjectExpert adapter with a Python health probe. Add an explicit backed-up kit upgrade that preserves deployment.env and rejects managed symlink replacement. Document cache-preserving retry and immutable release upgrade.

## Scope
No changes to chat model requirements, target project code, Git remotes or automatic Wiki authoring. Plain make platform-start remains parameter-free and core search remains independent of chat LLMs.

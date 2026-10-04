---
name: cache-aware-context
description: Structure selected skills, tool profiles, project policy, and task deltas for prompt-cache reuse and lower verified-task cost. Use when designing model requests, compacting a long session, comparing token cost, or changing an active tool/skill set.
compatibility: Provider-neutral; project scripts/prompt_manifest.py
---

# Cache-Aware Context

Optimize cost per verified success, not prompt length alone.

## Stable prefix

Order reusable request content consistently:

1. harness and project policy;
2. role;
3. stable tool schemas/profile in canonical order;
4. activated skill instructions in canonical order;
5. stable project profile/conventions.

Place the ContextPack, current task delta, latest tool output, diff, and error in
the volatile suffix. Do not insert timestamps, random request/session IDs,
changing counters, or shuffled tool definitions before a cache boundary.

After routing and repository reconnaissance, build a manifest:

```bash
python3 scripts/prompt_manifest.py \
  --role executor \
  --tool-profile native-code \
  --project-profile-hash sha256:<repo-profile-hash> \
  --skill systematic-debugging \
  --skill verification
```

The helper hashes policies and selected skill bodies, sorts skill identities,
and returns a generic cache key and intent. It does not send a model request.
The active client/provider adapter decides whether and how to apply explicit
cache controls.

## Compaction decision

Compact only when context pressure, stale-history dominance, or a phase change
is material and expected savings exceed lost prefix reuse. Write a
`session-checkpoint` first. Preserve exact source snippets by path/hash rather
than rewriting all code as prose.

Measure cached-input ratio, dynamic input, tool calls, latency, and cost per
verified success when the provider exposes them. Do not claim savings from a
manifest alone.

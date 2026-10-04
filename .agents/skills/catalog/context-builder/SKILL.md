---
name: context-builder
description: Build a bounded content-addressed ContextPack for planning, delegation, model handoff, or session compaction. Use when another agent/model needs selected project evidence without the whole repository or parent conversation.
compatibility: Python 3; project scripts/context_pack.py and ContextPack schema v1
---

# Context Builder

Select evidence in this order:

1. exact requested paths and text matches;
2. definitions, references, and relevant tests;
3. AST/dependency neighbors when structure requires them;
4. semantic or graph retrieval only when exact methods are insufficient.

Create a pack from the repository root:

```bash
python3 scripts/context_pack.py \
  --goal "<bounded objective>" \
  --acceptance "<observable result>" \
  --constraint "<must preserve>" \
  --file 'path/to/evidence::why this file is required' \
  --symbol Namespace.symbol \
  --command "<verification command>" \
  --write
```

The pack stores paths, hashes, sizes, symbols, commands, constraints, and
references—not source bodies or chats. Equivalent logical inputs produce the
same `CP-*` ID regardless of argument order.

## Handoff contract

Send only the objective, acceptance criteria, constraints, selected evidence,
verification command, tool profile, budget, and escalation condition. Do not
send parent chain-of-thought, unrelated files, the full wiki, all tools, or old
failed hypotheses.

The receiver must verify file hashes before relying on a stale pack. A
ContextPack does not grant tools, network access, or broader write authority.

# Task handoffs

This directory holds canonical structured task state. Each non-trivial task
that begins through `python3 scripts/session_state.py start` creates a JSON
file here (one per task). The active handoff is summarized in
[`../CURRENT.md`](../CURRENT.md).

Do not commit raw reasoning, secrets, or copied source into handoff files.
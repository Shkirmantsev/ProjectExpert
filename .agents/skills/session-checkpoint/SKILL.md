---
name: session-checkpoint
description: Create or restore compact, crash-safe project task checkpoints. Use for long or interrupted work, phase boundaries, handoffs, context compaction, explicit resume requests, or before stopping with meaningful work unfinished.
compatibility: Linux/Python 3; project scripts/session_state.py
---

# Session Checkpoint

Persist verified operational state, not conversation history or hidden
reasoning.

## Workflow

Start a checkpoint:

```bash
python3 scripts/session_state.py start \
  --goal "<goal>" \
  --acceptance "<observable condition>" \
  --todo "<first remaining step>" \
  --context "<relevant project path>" \
  --openspec-change "<change-id-if-any>"
```

The start command makes this the current task. At each material implementation
step, decision, blocker/failure, or verification result, update the current task;
the ID is optional:

```bash
python3 scripts/session_state.py checkpoint \
  --status verifying \
  --done "<verified result>" \
  --todo "<remaining result>" \
  --file path/inside/project \
  --next-action "<one safe next action>"
```

When a command or hypothesis fails, pass a compact stable fingerprint with
`--failure-fingerprint`. Repeated fingerprints and evidence-free checkpoints
are counted by the host-side runtime; `runtime.next_decision` becomes `reflect`
and then `escalate` at the configured limits. A status change or a rewritten
plan is not evidence of progress by itself.

Restore and validate file hashes before continuing:

```bash
python3 scripts/session_state.py resume
```

Exit code `3` means the recorded working set drifted. Re-inspect changed or
missing files before acting. Exit code `2` means the checkpoint request itself
is invalid. Pass `--id` only to select a non-current historical handoff.

## Store

- goal, observable acceptance conditions, OpenSpec change, and relevant context;
- done/todo/blocked state;
- verified decisions and verification results;
- project-relative file paths with SHA-256 hashes;
- bounded step use and the next safe action.

Do not store raw chats, chain-of-thought, credentials, copied source trees, or
large command output. Put bulky artifacts elsewhere and store only a path/hash.
Canonical checkpoints are project-visible JSON under `.ai/state/handoffs/`.
Every successful `start`, `checkpoint`, and `resume` atomically regenerates the
concise `.ai/state/CURRENT.md` view. Compatible legacy checkpoints under ignored
`tmp/local/sessions/` remain readable and are promoted when resumed or updated.
Local lock files remain ignored under `tmp/local/`.

At the start of an empty-dialog session, read `.ai/state/CURRENT.md`, then run
`resume` before making changes. Checkpoint before context compaction, handoff, or
the final response so the next session never depends on chat history.
`python3 scripts/session_state.py verify` fails if the generated view and its
canonical JSON differ; the normal harness check runs this gate.

Each repeated list option supplies the complete current value for that field.
Use `--clear todo`, `--clear blocked`, or `--clear pending-verification` after
resolving them. Completion is rejected while todo/blocked items or pending checks
remain, and still requires recorded passing verification.

## Safety

The script rejects working-set files outside the repository. A checkpoint does
not authorize writes, network access, delegation, or continuation past an
approval boundary.

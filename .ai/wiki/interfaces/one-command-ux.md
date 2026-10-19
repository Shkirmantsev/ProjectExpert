---
id: interfaces.one-command-ux
title: One-command production UX
kind: interfaces
status: active
summary: CLI + first-start wizard + admin REST routes that give the operator a single `start` command and a `models` command group. The web control plane exposes four administrative endpoints that require the `administrator` capability.
sourceRefs:
  - pi_platform/cli/main.py
  - pi_platform/core/control/retrieval_settings.py
  - pi_platform/core/retrieval/first_start_wizard.py
  - pi_platform/adapters/ui/retrieval_admin_routes.py
  - openspec/changes/production-semantic-search-and-branch-reconciliation/specs/2026-10-18-one-command-production-ux/spec.md
maintenance:
  mode: authored
related:
  - modules.release-gate
  - modules.retrieval
---

# One-command production UX

The production UX surface: one `start` command, a `models`
command group, a first-start wizard rendered by the web
control plane when no model selection exists, and four
administrative REST endpoints that require the
`administrator` capability.

## CLI surface

The existing `pi_platform/cli/main.py` parser grows two new
top-level subparsers:

- `python -m pi_platform.cli start --target PATH --model {gemma,qwen} --device {auto,cpu,cuda}` —
  loads `RetrievalSettings` (or runs the wizard when none
  exist), then calls `build_production_retrieval_runtime()` and
  prints `Bootstrap ready at http://127.0.0.1:8765`.
- `python -m pi_platform.cli models list | status | pull <alias> | verify <alias> | use <alias>` —
  `list` reads the production-enabled set from
  `distribution/licenses/model-licenses.json`; `status` reports
  the active profile; `pull` and `verify` operate on the local
  HF cache (verify checks `sentence_bert_config.json` +
  `tokenizer.json` + `config.json`); `use` records the new
  selection in settings.

The default `start` flow MUST NOT require the user to run any
of the `models` sub-commands explicitly.

## Retrieval settings

`pi_platform/core/control/retrieval_settings.py` —
`RetrievalSettings` (frozen dataclass with validating
`__post_init__`) + `load_retrieval_settings()` (missing file →
defaults, malformed → raises, never silent reset) +
`save_retrieval_settings()` with atomic `.tmp` + fsync +
`os.replace`. The settings file lives at
`.project-intelligence-cache/retrieval-settings.json`.

## First-start wizard

`pi_platform/core/retrieval/first_start_wizard.py` —
`FirstStartWizard.render/should_render/submit`. The wizard
ONLY renders when `bootstrap_state == 'not-started'`; it
offers EmbeddingGemma 2 + Qwen3-Embedding-0.6B, the
`auto` / `cpu` / `cuda` device choice, the Docling toggle and
the single `initialise_and_build_index` action. `submit()`
validates the form and returns a `RetrievalSettings`.

## Administrative REST routes

`pi_platform/adapters/ui/retrieval_admin_routes.py` —
framework-free dispatcher over a route table:

- `GET /api/v1/admin/retrieval` — current settings
- `PUT /api/v1/admin/retrieval` — update settings; refused
  with HTTP 403 + structured error when the caller
  capability is not `administrator`
- `POST /api/v1/admin/models/pull` — accept `{alias}`, return
  `{job_id, status: 'queued'}`
- `POST /api/v1/admin/reindex` — return
  `{job_id, status: 'queued'}`
- `GET /api/v1/admin/jobs/<job_id>` — return
  `{job_id, status, progress_pct, message}`

Non-admin paths pass through to the host application; structured
errors are exactly `{"error", "code", "details"}`.

## How to fix when something breaks

- **Wizard never renders** — check `bootstrap_state` in
  `RetrievalSettings`; the wizard only renders for
  `not-started`.
- **PUT /api/v1/admin/retrieval refuses a legitimate admin** —
  check the `caller_capability_provider` wiring; the route
  expects the literal string `administrator` for model
  switches.
- **`start` fails before reaching bootstrap** — the most
  common cause is a missing model in the local HF cache; pull
  it with `models pull <alias>` first.
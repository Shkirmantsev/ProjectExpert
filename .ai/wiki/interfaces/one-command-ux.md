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
  - openspec/specs/2026-10-18-one-command-production-ux/spec.md
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
  opens the HTTP control plane before model loading or indexing, with readiness
  false. A worker loads settings, hydrates, discovers sources and builds a
  candidate retrieval runtime. It publishes the runtime and successful version
  snapshot before readiness becomes true. Saved model/device choices survive
  restart unless explicitly overridden. `--no-serve` performs a one-shot build
  and exits; serving is the default.
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
validates the form and returns a `RetrievalSettings`. HTTP submission persists
`not-started`, never `ready`; the serving monitor picks up model/device changes.
The UI polls `/api/v1/indexing-status` every three seconds. Model failures leave
HTTP and setup accessible while retrieval returns 503; failed builds retry.

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

The running control plane executes queued reindex and model-download jobs in
background workers, records completion/failure, and serializes index mutation
with the same project lock as automatic refresh.

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

## Live operator selection

A wizard/admin model or device selection becomes a runtime command override
for the current service, so it can supersede initial environment defaults and
survive later branch refreshes. A process restart resolves documented startup
precedence again. Applying unchanged settings explicitly schedules a refresh,
so readiness cannot remain false merely because the file fingerprint is the
same. First bootstrap resolves project defaults before creating local settings;
it cannot silently manufacture a Gemma choice over a configured Qwen default.

## Standalone deployment kit

`distribution/deployment/` contains product-only Compose, non-secret defaults,
Make targets and Bash/PowerShell launchers. The `deployment-kit` Containerfile
stage exports them without overwriting existing files. Published kits bind the
runtime to a tested image digest. The kit default selects Qwen Q4_K_M in a managed CPU sidecar and automatically
downloads weights into persistent model storage. Startup waits for HTTP retrieval
readiness for up to 30 minutes. Windows uses Docker Desktop's Linux engine.
Office GPUs require no special driver for CPU operation. Optional pinned Gemma/Qwen
GGUF Vulkan/CUDA runtimes use Linux sidecars or a native Windows service; setup
also downloads their weights. Physical GPU and Windows validation remains pending. See [installation](../../../docs/PRODUCTION_INSTALL.md).

Model and accelerator selection are independent in the kit. `gemma` plus a GPU
backend selects `gemma-gguf` with its pinned multimodal projector; `qwen` plus
CPU stays native Qwen CPU. Explicit GGUF aliases can also run in a CPU sidecar.
GGUF profiles have distinct cache identities and Gemma preserves image inputs.

After successful bootstrap, persisted ready-state model/device settings reflect
the effective runtime selection, including deployment environment overrides;
a prior CPU model must not remain displayed after a GGUF/GPU switch.

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
  - pi_platform/core/inference/profile.py
  - openspec/specs/2026-10-18-one-command-production-ux/spec.md
maintenance:
  mode: authored
related:
  - modules.release-gate
  - modules.retrieval
  - modules.inference-runtime
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

- `python -m pi_platform.cli start --target PATH --model {gemma-torch,gemma} --device {auto,cpu,cuda}` —
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

The same layer owns the operator-visible retrieval defaults.
ProjectExpert ships one embedding model: EmbeddingGemma 2 in the
pinned Q8_0 quantisation (the native Transformers binding of the
same checkpoint stays an explicit `gemma-torch` opt-in). The
retired Qwen3-Embedding-0.6B aliases are rejected with an
actionable message naming the supported aliases — in settings
(`RetrievalSettings`), in the runtime configuration resolver
(`PI_EMBEDDING_MODEL`) and in the embedding factory — instead of
being silently substituted. BM25-light reranking is active by
default (`reranking_enabled`, family `bm25-light`) and is
operator-controllable through the settings file, the
`PI_RERANKING_ENABLED` override and the per-query
`enable_reranking` argument on `project.search` /
`project.retrieve_context`.

Note: the accepted
[`one-command-production-ux` spec](../../../openspec/specs/2026-10-18-one-command-production-ux/spec.md)
and the CLI / wizard paragraphs of this node still describe the
retired Qwen3 choice and the older `--model {gemma,qwen} --device
{auto,cpu,cuda}` flags. The implemented consolidation
(`consolidate-embeddinggemma2-and-autoconfigure-inference`)
supersedes them; this node records the observed implementation
and reports the spec lag rather than hiding it.

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
runtime to a tested image digest. The kit defaults to Gemma Q8_0 with its pinned
projector and a managed inference service. Startup waits for retrieval readiness
for up to 30 minutes. Auto selection measures usable GPU inference against CPU;
failed candidates fall back to CPU. Linux uses sidecars; Windows GPU inference
uses a native service with compatible drivers. CPU operation requires no GPU.
Standalone application/container Make targets default to `gemma-torch`.
See [installation](../../../docs/PRODUCTION_INSTALL.md).

GGUF and native profiles have distinct cache identities; Gemma preserves image
inputs. Physical hardware and registry publication acceptance remain separate.

After successful bootstrap, persisted ready-state model/device settings reflect
the effective runtime selection, including deployment environment overrides;
a prior CPU model must not remain displayed after a GGUF/GPU switch.

## Automatic backend selection

The deployment no longer asks the operator to pick the runtime
backend by hand. `python -m pi_platform.cli inference plan`
(`pi_platform/core/inference/`) reads probe evidence and selects
the backend automatically in `cuda -> vulkan -> cpu` order: a
candidate wins only when the runtime's own `--list-devices`
reports a usable, non-software device of that backend. An
unavailable or unusable GPU is a downgrade to the validated CPU
profile — startup continues on CPU instead of failing. The
launchers parse the printed decision JSON and apply it; on any
plan error they fall back to the validated CPU profile. See
[`modules/inference-runtime`](../modules/inference-runtime.md).

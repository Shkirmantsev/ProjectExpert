# Project Intelligence deployment

Run `bash start.sh` on Linux or `powershell -File start.ps1` on Windows.
Alternatively run `make platform-start` (GNU Make required). Windows uses
Docker Desktop with WSL2 and Linux containers. Docker Compose 2.30+ is required
for the optional CUDA profile; the CPU profile needs Compose 2.20+.

## Commands

`make` and `make help` **only list the commands**. They need neither Docker,
Python nor `deployment.env`, and they change nothing:

```bash
make            # prints the command list
make help       # prints the same command list
make platform-start
```

Startup is always explicit. Before this change a bare `make` started the
deployment; it now prints the command list, so any script that relied on bare
`make` must call `make platform-start` (or `bash start.sh`) instead.

`make help` lists every public target with a one-line description: `help`,
`platform-start`, `platform-stop`, `platform-status`, `platform-logs`,
`platform-pull`, `platform-restart`, `platform-init`, `platform-hydrate`,
`platform-materialise`, `platform-models`, `platform-model-pull`,
`platform-reindex`, `platform-doctor`, `eval`, `eval-retrieval`,
`eval-chunk-size-sweep`, `invariants` and `metrics-gate`.

The target repository defaults to the parent directory. Set PI_TARGET_REPO in
`deployment.env` to change it; use forward slashes for Windows paths. The target
must already exist. First startup seeds the reviewed offline OCI asset image,
then verifies local embedding, tokenizer and Docling assets. Registry pulls still
require the engine's normal TLS/enterprise trust; setup/indexing do not download
models from HF/GitHub. Missing reviewed release pins stop startup with an explicit
error. The asset release is currently blocked; see the release gate below.
The launcher timeout is 30 minutes. Success requires retrieval readiness.

## The reported address

After readiness the launcher prints the effective address, for example
`Ready: http://localhost:8765`. The port is resolved the same way Compose
resolves it: the shell environment overrides `deployment.env`, `deployment.env`
is read as plain text (it is never executed as shell code), and `8765` is the
fallback. Set `PI_CONTROL_PORT` in `deployment.env` or export it in the shell
before starting. A failed readiness never prints `Ready:` and always returns a
nonzero exit code.

## Models and hardware

ProjectExpert ships **one** embedding model: **EmbeddingGemma 2**, quantised
`Q8_0`, served by a pinned `llama.cpp` runtime. The pinned package is the
`Q8_0` backbone **plus** the `Q8_0` multimodal projector, so text, image,
audio and video embeddings are all available. The retired alternative
embedding model is no longer selectable, is no longer a setup option and is
not part of any deployment profile.

| PI_EMBEDDING_MODEL | Execution |
|---|---|
| gemma (default) | pinned EmbeddingGemma 2 Q8_0 GGUF (backbone + projector) through the managed `llama.cpp` runtime |
| gemma-torch | native Transformers binding of the same checkpoint; explicit opt-in; text and image only; needs `torch` |

### Automatic backend selection

`PI_ACCELERATOR=auto` (the default) detects the backend on the machine and
starts the deployment with the best **validated** profile:

```
CUDA  ->  Vulkan  ->  CPU
```

The order is a preference, not a requirement. A candidate is only selected
when the runtime itself proves it can use a device: the launcher asks the
runtime for its device list and the device must be reported. A software
rasteriser (lavapipe, SwiftShader) is never selected, and the multimodal
projector always stays on the CPU because its ~555 MB of Q8 weights plus
runtime buffers do not fit a small integrated-GPU allocation safely.

**A GPU that is not measurably faster is also not selected.** The GPU is an
optimisation, so the launcher measures it: the CPU baseline and every
validated GPU candidate are started, measured with the same fixed corpus and
stopped again before the winner is started for real. A GPU candidate is only
selected when it is at least **1.10x faster** than the CPU baseline. A GPU
that works but is slower is rejected with that reason and the CPU profile is
used.

**An unavailable or unusable GPU is a downgrade, not a failure.** The
deployment falls back to the validated CPU profile, reports which candidates
were rejected and why, and keeps serving. The same is true for an explicitly
selected backend that does not validate. An explicitly selected backend is the
operator's decision and is not second-guessed by the benchmark.

| Host | Selected |
|---|---|
| NVIDIA GPU with a working driver / container toolkit | CUDA |
| NVIDIA GPU without the container toolkit, or an AMD/Intel GPU with a Vulkan driver | Vulkan |
| Integrated / office graphics driver, or no GPU | CPU |

The CPU profile is the reference mode and never requires a GPU driver, the
CUDA toolkit or a Vulkan SDK. The launcher never installs or upgrades drivers.

`PI_ACCELERATOR` may still be set to `cpu`, `vulkan` or `cuda` to skip the
detection; an explicit choice that does not validate still degrades to CPU.
`PI_GPU_DEVICE` pins a specific device (for example `Vulkan1` or `CUDA1`); it
is honoured only when the runtime actually reported that device.

### What is supported and what is not

* **ROCm / HIP is not supported.** There is no AMD ROCm backend, and no ROCm
  runtime is shipped or downloaded. An AMD GPU is served through Vulkan when
  a Vulkan driver is present, otherwise through the CPU profile.
* No CUDA toolkit, Vulkan SDK or driver is ever installed on a client
  machine. The Linux GPU profiles use the pinned official runtime images; the
  Windows GPU profile uses the pinned native release archive.
* The runtime flags are passed as an explicit argument vector. The
  `LLAMA_ARG_*` environment variables are deliberately **not** used for
  inference flags: llama.cpp's variable names differ from its flag names
  (`--batch-size` is `LLAMA_ARG_BATCH`, `--ubatch-size` is `LLAMA_ARG_UBATCH`,
  `--parallel` is `LLAMA_ARG_N_PARALLEL`) and a wrong name is silently
  ignored.

### Physically verified vs. conditional

| Configuration | Status |
|---|---|
| Linux, CPU only, `llama.cpp` b11515 | **verified**: real inference, text + image + audio + video embeddings, 768-dimensional unit-norm vectors |
| Linux, Vulkan (AMD integrated GPU) | **verified**: the device is detected, the runtime offloads to it, all four modalities return valid vectors, and the CPU/Vulkan parity gate passes |
| Linux, automatic backend selection | **verified**: the launcher probes, measures and selects; on the verification host it correctly rejected a working-but-slower Vulkan profile |
| Linux, CUDA | conditional: the runtime image, the device selection and the `--fit` budget are implemented and probed, but no NVIDIA hardware was available for this verification |
| Windows, any backend | conditional: the launcher implements the same duty list and the native runtime is pinned, but no Windows host was available for this verification |

### Measured on the verification host

AMD Radeon Graphics (RADV RENOIR), integrated GPU, 512 MiB dedicated VRAM
carve-out, Mesa 25.2.8, Vulkan 1.4.318, llama.cpp b11515:

| Measurement | Value |
|---|---|
| Device reported by `--list-devices` | `Vulkan0: AMD Radeon Graphics (RADV RENOIR) (32334 MiB, 30768 MiB free)` |
| CPU / Vulkan cosine parity (text, image, audio, video) | 0.999945 / 0.999929 / 0.999911 / 0.999953 (gate: >= 0.995) |
| Vulkan embedding latency (median of 30) | 30.77 ms -> 32.50 emb/s |
| CPU embedding latency (median of 30) | 22.19 ms -> 45.06 emb/s |
| Measured speed-up | 0.72x -- **below the 1.10x gate, so the CPU profile is selected** |

The integrated GPU produces numerically equivalent embeddings but is slower
than the CPU for this workload, so the automatic selection keeps the CPU
profile. The Vulkan profile itself remains available and is used when the
operator selects it explicitly.

See `tmp/local/mm-run/evidence.md` in the development repository for the raw
measurements behind these statements.

### Windows specifics

Windows uses Docker Desktop with Linux containers. The CPU profile runs the
managed sidecar container. When a GPU candidate validates, a pinned **native**
`llama-server` is started on the host instead, and the application reaches it
through `host.docker.internal:8769`; it does not require Vulkan passthrough
into Docker. The native service listens on 127.0.0.1 with a per-run bearer
token stored in `accelerator/llama-api-key`; the token is never printed.
Permit access only from Docker/WSL in Windows Firewall, not public networks.
Run `powershell -File stop.ps1` before switching models or backends, then
start again. Linux uses `make platform-stop` before switching.

### Cache and maintenance

CPU/model state persists in the model-cache volume. Windows GPU assets persist
in accelerator/. Linux GPU weights share model-cache. `make platform-stop`
keeps caches. Never use `down -v` unless deleting cached assets intentionally.

Use `make platform-models`, `make platform-doctor`, `make platform-reindex`,
`make platform-logs`, `make eval`, `make eval-retrieval`, or
`make eval-chunk-size-sweep`. Eval targets use the bundled fixture benchmark;
repository evaluation requires a repository-specific golden set. The UI defaults
to http://localhost:8765, bound to loopback. Materialisation needs APPROVAL_TOKEN.

Published kits pin the tested application image digest and pinned accelerator
assets. To upgrade, export a new kit into a separate directory, compare files,
then update your existing kit deliberately. Export never overwrites your files.
Use `docker run --pull=always` when fetching a branch-tagged kit; otherwise
Docker may reuse a cached older image. Wait for the production publication job
for the desired merge, not just the independent core-image job. To inspect the
current kit pin without exporting files:

```bash
docker run --pull=always --rm --entrypoint cat ghcr.io/shkirmantsev/project-intelligence-deployment:dev /bundle/compose.yaml
```

An existing `PI_IMAGE` in `deployment.env` or the shell overrides the Compose
pin. Update that override to the new kit's digest for an image-only upgrade,
then run `start.sh` / `start.ps1` to recreate the service. A container restart
does not change its image. Preserve local configuration and any sidecar patches.

Application startup checks ownership support **before running CLI writers**.
An image from before project-owner execution is refused with an `Incompatible
ProjectExpert image` error. This also protects direct Compose invocation without
`deployment.env` and explicit `PI_IMAGE` overrides. Upgrade both the exported kit
and its application image; do not remove the guard to run an old pin. No manual
`PI_IMAGE`, UID or GID is required for a normal quick start: published kits retain
their verified matching default image.

New Wiki articles written through MCP have POSIX mode `0644`. Updating an article
or navigation index preserves its existing permissions, including deliberately
private `0600`/`0640` modes. Files already created by an old root-run image may
need a one-time, reviewed owner/access repair; the platform does not recursively
chown canonical sources. A manual permission repair will now survive subsequent
atomic updates. Runtime state and credentials remain private.

SHA tags are retained without an automatic expiry/cleanup job. Registry owners
can delete packages; keep a local archive if permanent independent retention
is required. Files also live in Git under distribution/deployment/.

## Diagnostics

The inference runtime has its own diagnostic commands:

```bash
# inside the application container
python -m pi_platform.cli inference doctor --evidence-b64 <base64>
python -m pi_platform.cli inference plan --evidence-b64 <base64>
python -m pi_platform.cli inference status
```

`plan` prints exactly one JSON object: the selected backend and device, the
fit budget, every rejected candidate with its reason, the runtime argument
vector and the Compose environment fragment. The launchers use the same
command, so the Linux and Windows launchers cannot drift apart.

### "Found orphan containers" during startup

Compose reports a container as an orphan when the running container belongs to
a service that the invoked Compose configuration does not declare. The launcher
used to ask the inference plan and the benchmark with the base `compose.yaml`
only, so the running `embeddings` and `model-setup` sidecars looked like
orphans while the sidecar deployment was healthy.

Every launcher invocation now uses the complete applicable topology: the
production service, the `model-setup` one-shot and the `embeddings` sidecar
are always declared together. The inference plan runs before the backend is
known and therefore uses the provisional CPU overlay; it still starts only the
production service (`--no-deps`).

Consequences:

* A repeated startup no longer reports the sidecars as orphans, and it never
  deletes the sidecars, the downloaded model assets or the indexed data.
* A genuinely unrelated container in the same Compose project is still
  reported. Nothing is removed automatically: the launchers never pass
  `--remove-orphans`, and `stop.ps1` stops the complete service topology
  instead of deleting whatever it does not recognise.
* Switching the embedding model or the backend between the sidecar and the
  native Windows runtime changes the service set. Stop the deployment first
  (`make platform-stop`, `powershell -File stop.ps1`) so the previous
  containers are removed deliberately.

## Recovery and cache maintenance

Refresh failures retry without another source edit. Real edits made during indexing
keep readiness false until a coherent pass completes. Generated `distribution/sbom/`
files are excluded; other distribution source files remain indexed.

MCP clients should use Streamable HTTP at `/mcp`. GET returns 405 (no standalone
SSE stream); initialize and tools/list use POST. The endpoint is not a legacy SSE URL.

Native Hugging Face downloads and `models pull/verify` share `PI_MODEL_CACHE/hub`.
To reclaim abandoned partial downloads from either the old or current layout:

```bash
bash compose.sh exec -T production python -m pi_platform.cli models prune-incomplete
```

This removes only `.incomplete` blobs older than 24 hours whose downloader lock
can be acquired. Completed weights and active downloads are retained. Setup
removes its temporary file on failed downloads. The Gemma Q8_0 package has a
distinct vector profile from the retired model; upgrading rebuilds the vectors
once. Existing kits preserve their configuration on export: copy the updated
launcher/Compose files and deliberately set `PI_EMBEDDING_MODEL=gemma` when
upgrading.

## Search UI and private document inbox

Search and ranking require the managed Gemma embedding runtime, not a generative
chat LLM. The UI initialization action waits for readiness; reindex shows its
queued/running/completed/failed job. HTTP 503 during a refresh protects against
serving stale evidence; the status panel and logs expose the actual reason.

Put private Markdown/text/HTML/PDF sources below `tmp/local/source/` in the
**target repository**, including subfolders. Automatic indexing includes this
inbox and preserves LOCAL_ONLY policy. Hydration adds its path to
`.git/info/exclude`; confirm with `git check-ignore` before adding private files.
Other local runtime scratch remains excluded. PDF conversion uses Docling and
may provision its pinned assets on first use. Extracted chunks remain local;
curated `project-knowledge/wiki/` articles require an explicit calling-agent
write and review.

The optional chat section now saves a real server-side OpenAI-compatible or
Anthropic connection: enter its /v1 base URL, exact chat model and provider key,
allow context sharing, enable generated answers, Save and Test. Search remains
independent. PI_OPENAI_BASE_URL is legacy adapter metadata; the new settings are
in private ignored runtime state. The kit includes a Linux host-gateway mapping
for LM Studio on the Docker host. Active mode reports effective embedding
CPU/GPU/Hybrid separately from requested Auto, with evidence and limitations. Open WebUI, when separately installed on the same Compose network,
can use `http://production:8765/v1`, model `project-intelligence`, to display cited
search evidence (plus the optional generated answer) through JSON or finite SSE. Its connection settings persist
independently and may need updating. API authentication and signed materialisation
approval are separate credentials; normal search needs no materialisation token.
Complex tasks belong in a connected MCP agent with its own LLM.

`Test saved connection` sends a public prompt without project excerpts and allows
up to 512 output tokens, since reasoning can consume the same budget as the
final answer. If that budget is exhausted before any final text, the diagnostic
reports the output limit rather than incorrectly identifying the model as an
embedding model. The probe waits up to 30 seconds. Generated project answers
allow up to 4096 output tokens and 10 minutes for slower local reasoning models;
reasoning can consume part of that budget. The UI shows any generation failure
before the retrieved sources. Deterministic retrieval never waits for chat.

### Optional LLM binding before startup

Configure without a running service:

```bash
make platform-llm-configure LLM_PROVIDER=openai LLM_URL=http://host.docker.internal:1234/v1 LLM_MODEL=your-chat-model LLM_SHARE_CONTEXT=1
make platform-start
```

Or combine both steps:

```bash
make platform-start LLM=1 LLM_PROVIDER=openai LLM_URL=http://host.docker.internal:1234/v1 LLM_MODEL=your-chat-model LLM_SHARE_CONTEXT=1
```

`LLM=1` configures/enables before starting; omitted `LLM` preserves saved settings;
`LLM=0` disables chat before startup. Invalid configuration prevents startup.
Use `LLM_PROVIDER=anthropic` and `LLM_URL=https://api.anthropic.com/v1` for an
Anthropic API account. Export `LLM_API_KEY` in the environment if authentication
is required; never put the key value in Make arguments. The one-shot container
receives variables by name and prints redacted settings. Fresh enablement
requires explicit `LLM_SHARE_CONTEXT=1`.

`platform-llm-status`, `platform-llm-test` and `platform-llm-disable` are also
available before startup. They require the updated application image. The URL
and model are the same fields shown and edited in UI section 11; later UI edits
apply immediately and persist across restarts.

### Target tmp documents

Untracked supported documents under the target's `tmp/` are private recursive
inputs too, for example `tmp/reports/2026/portfolio.pdf` and `tmp/notes/brief.md`.
They use LOCAL_ONLY policy and the local inbox byte limit (default 256 MiB),
including when Git ignores tmp. Hydration/start adds `/tmp/` to `.git/info/exclude`;
verify with `git check-ignore tmp/notes/brief.md` before adding private files.
Existing tracked files remain tracked and use normal repository eligibility.
Runtime/cache/build/vendor trees remain excluded. `tmp/local/` remains reserved
for generated local state, except `tmp/local/source/` (or an explicitly configured
source inbox), which stays searchable. PDF extraction is automatic; synthesis of
curated Wiki pages remains an explicit agent task.

## Linux file ownership

The exporter may run as root inside its short-lived container, but on POSIX
filesystems the exported `.project-intelligence-deploy/` and managed files are
assigned to the mounted project's owner. Re-export also repairs an existing
root-owned kit, including preserved `deployment.env` and generated backups,
without replacing operator settings. Existing non-root kit ownership is retained.
It does not recursively chown your project or follow symlinks/hardlinks to change
external ownership. Export into an existing user-owned project directory; if the
project parent itself belongs to root, repair that parent separately first.

The updated **application image** also repairs existing root-owned
`.project-intelligence-cache/` entries before running CLI handlers as the project
UID/GID. Indexing, UI jobs and later CLI writes then create user-owned files,
including after restart. Startup preserves cache contents and prepares access to
the dedicated model cache and internal embedding key. The repository itself is
not recursively reassigned. No operator UID/GID variables are required. The host
CLI is unchanged. Custom external cache paths must already be writable by that
user; external inputs and credentials must be readable by the application user.
Cache HOME is kept under `.project-intelligence-cache/home/`.

This persistent cache fix requires recreating the service with the new application
image. A repaired exporter alone cannot change an old running application's UID.
Model-setup and embedding sidecars keep their existing execution identities.

For an older kit that created root-owned entries, re-run export with the updated
deployment-kit image; `--upgrade` is optional for ownership repair and replaces
templates only when explicitly supplied. A locally rebuilt image must be used
until this fix is published; pulling an older registry image cannot apply it.

## Upgrade, embedding capacity and optional Open WebUI

The exporter preserves existing files by default. To update an installed kit,
pass `--upgrade` to the **new** kit image. Managed templates are replaced with
backups under `.kit-backups/`; operator `deployment.env` and unrelated files are
preserved. Review old Compose customizations in those backups. Set the supported
operator choices in `deployment.env`, rather than patching generated arguments.
The published kit embeds its matching application digest; a `PI_IMAGE` override
still takes precedence.

Native and managed embedding defaults now use 4096 for context, batch and
microbatch with one parallel slot. The former 1024 batch setting could reject
1049-token project chunks. Oversized arbitrary inputs remain bounded by the
model/runtime; these defaults are not an unlimited-input promise.

For the optional chat frontend, add `COMPOSE_PROFILES=open-webui` to
`deployment.env` and use ordinary `make platform-start`. Its default loopback
port is 8768 (`PI_OPEN_WEBUI_PORT` overrides it); the frontend connects internally
to `http://production:8765/v1` and exposes model `project-intelligence`.
Set `PI_WEBUI_NAME` in `deployment.env` for a custom frontend name; the managed
template maps it to `WEBUI_NAME`, so future kit upgrades retain the choice.
`PI_OPEN_WEBUI_API_KEY` is needed only when the ProjectExpert adapter requires
an API bearer key. ProjectExpert search does not require a chat LLM. Existing
Open WebUI databases may retain Admin Connections settings; update the endpoint
there if needed. The kit overrides the pinned image's jq probe with Python.

After fixing an embedding service, use the UI's Trigger reindex or stop/start
bootstrap to recover. Do not delete the runtime cache: it contains reusable
vectors and saved chat settings. See the source repository's
`docs/PORTABLE_DEPLOYMENT_RUNTIME_REPAIR.md` for a complete trade-analyzer upgrade.

## Change embedding execution in the UI

With the updated application **and kit**, select the embedding binding and
Execution device, then press **Apply model & device and build index**. This
persists an explicit operator override in the target's ignored
`.project-intelligence-cache/runtime-selection.json`, applies it before indexing
and survives application/container restart. The page follows a background job;
failure stays visible. Selecting a dropdown alone does not apply a change.

Gemma is one checkpoint with two bindings: managed GGUF Q8_0 and native
Transformers. Native requires its libraries and the installed verified local pack; explicit developer mode may download
separate weights. Its available hardware depends on the installed PyTorch build;
the standard production image contains CPU PyTorch. A native-only deployment
without a configured GGUF endpoint does not offer the unavailable GGUF binding.

The managed sidecar now runs an authenticated child-process controller on
internal port 8770, using the existing embedding API key. It changes only
the fixed child process. Setup provisions its stdlib-only Python from the pinned
application into the model volume; sidecars need no system Python or network
package install. Device probes still work before setup on an empty cache.
The controller changes only
llama-server device/fit flags, validates health and restores the previous child
on failure. It has no Docker socket and no published control port. Linux exposes
an existing `/dev/dri` tree even for CPU-first startup so Vulkan can later be
selected in the UI. CUDA still needs the CUDA image and NVIDIA passthrough at
startup (`PI_ACCELERATOR=cuda`); UI cannot add hardware or replace container images.
GPU failure at launch retains the existing CPU fallback policy; an unavailable
explicit UI GPU selection reports a failure instead of claiming success.

Auto compares CPU/GPU median latency using the launcher's fixed query corpus,
keeping GPU only at >=1.10x speedup. A later refresh reuses this result while the
controller generation is unchanged. **Active mode** reads the current process:
CPU, or Hybrid for a GPU backend with CPU projector. It does not promise a measured
GPU layer count. Legacy remote endpoints and native Windows GPU services have no
live child controller; the page explains that their hardware must be configured
on their host. Native in-process bindings apply supported device choices directly.

## What PI_UI_TOKEN means

`PI_UI_TOKEN` is an optional operator-chosen bearer password protecting
ProjectExpert's REST/MCP/OpenAI-compatible API, including settings changes. It is
not an embedding requirement, provider API key or knowledge approval token. It
is unset by default for a loopback-only local installation: there is no generated
token to find, and the UI disables the empty token field with an explanation.

To enable it, generate a random secret privately, set `PI_UI_TOKEN` in the shell
environment used by Compose and recreate production with `make platform-start`.
For example, in Bash: `export PI_UI_TOKEN="$(openssl rand -hex 32)"`. Store the
value in your password manager/ignored private environment, never Git. Obtain an
existing configured value from that private environment or its operator; the UI
cannot reveal it. Paste it into the page when requested (kept in tab memory).
Configure the same bearer value privately in MCP clients and Open WebUI
(`PI_OPEN_WEBUI_API_KEY`). Public `/api/v1/auth-status` reveals only whether it is
required, never its value. No authentication is silently enabled by this upgrade.


## Agent Skills over MCP (SEP-2640)

The application image includes the `project-intelligence` Agent Skill and its
reference documents. Nothing needs to be copied into a new target project, and
no chat model or environment variable is required for skill discovery.
Connect your agent to the deployment's existing MCP endpoint, for example
`http://127.0.0.1:8765/mcp` (use your configured published control port).

The server advertises `io.modelcontextprotocol/skills` in `server/discover` and
legacy `initialize`. A client with native support can list the skill with
`skills/list`, obtain its complete manifest with `skills/get`, and lazily read
`skill://project-intelligence/SKILL.md` and its references using `resources/read`.
Each manifest includes the complete frontmatter, file sizes and SHA-256 digests.
The server does not implement the optional `resources/directory/read` method;
all supporting files are already enumerated in the manifest.

For a quick operator check (adjust the port if needed):

```bash
curl -sS http://127.0.0.1:8765/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"skills/list","params":{}}'
```

If your operator enabled API authentication, supply its existing bearer token
through your client's secure credential configuration. The command above
assumes the default local deployment without API authentication.

Native skill activation depends on the MCP client. Reading `SKILL.md` alone
does not install or activate a skill and never grants extra tool permissions.
For a client without the extension, ask it to read
`skill://project-intelligence/SKILL.md` and the needed relative references from
this MCP server using ordinary MCP resources. If the client does not expose
resource reads, use the existing vendor skill package/local installation path.
Keep approvals and caches scoped to the originating MCP server, not only the URI.

The extension is currently Beta; SEP-2640 itself is Final. Protocol references:
[Skills specification](https://skills.extensions.modelcontextprotocol.io/specification/beta/skills),
[SEP-2640](https://modelcontextprotocol.io/seps/2640-skills-extension).
Upgrading source alone does not update deployed containers: rebuild/publish the
application image, update the deployment kit's image pin, recreate the application
container, and reconnect the MCP client to refresh discovery.

## Managed workspace (opt-in)

Set `PI_WORKSPACE_MODE=volume` in `deployment.env` to use the packaged native helper. `auto` and `bind` retain direct host mounts. Mutating `up`, `run`, and `restart` prepare and synchronize before application execution. `up` and `restart` start session supervision; `config`, logs, and status never initialize storage. The generated `workspace.env` is persistent local state; do not edit it. Normal shutdown requests a verified checkpoint before stopping supervision and retains both volumes. Backup failure is reported but does not prevent shutdown.

The default supervisor is session-only. For explicit per-user login startup, run `bash workspace-autostart.sh install` on Linux (systemd user session) or `./workspace-autostart.ps1 -Action Install` on Windows (Task Scheduler). These commands register a task only when invoked; launchers never register one. Remove using `uninstall` / `-Action Uninstall`. Linux login startup does not imply system-wide lingering. Windows native login execution requires platform acceptance testing.

Release kit images contain Linux amd64 and Windows amd64 helper binaries and `workspace-agent-SHA256SUMS`; wrappers verify the selected binary before execution. A source-only template export lacks these release-built executables and cannot start volume mode until they are supplied with matching checksums.

## Liveness and indexing readiness

`start.sh` / `start.ps1` waits for `/health`, then returns while the background
indexer continues. `/health/ready` retains the consistency gate. Use
`bash ./wait-ready.sh` or `.\wait-ready.ps1` when a complete retrieval index is
required before continuing. A live process with failed indexing stays live;
inspect `/api/v1/indexing-status` and logs for indexing failures.

## Enterprise certificate trust

On `up`, launchers collect host public root certificates into the ignored
`host-trust/` directory and merge them with the image's public CA roots at
container startup. `PI_HOST_CA_MODE=off` disables import. TLS and hostname
verification remain enabled. The optional `PI_EXTRA_CA_BUNDLE` names a path
**inside the container** and requires an explicit mount when used.

The Docker daemon must already trust GHCR before it can pull any image,
including this kit. A container CA bundle cannot fix a failed registry pull.
An `x509`/unknown-authority error during pull belongs to the Engine/Desktop/
Rancher trust/proxy configuration. Configure that engine's approved corporate
CA or preload images through an approved air-gap process; retain TLS checks.
Application HTTPS failures after startup belong to the container trust boundary.
The launchers do not modify Docker credential helpers, `~/.docker/config.json`,
or the host PATH. For a credential-helper failure, inspect `docker context show`,
the selected Docker config and the reported helper executable; use a scoped
`DOCKER_CONFIG` directory when organizational policy requires a separate config.

## Offline asset release gate

On Windows, CUDA first probes the pinned managed container when the Docker
engine exposes NVIDIA acceleration. The container carries application runtime
libraries and uses the host driver; it installs no host toolkit or driver.
Unavailable container acceleration falls back through the existing validated
native/CPU policy. Native Vulkan is included in the default asset pack; native
CUDA is optional and requires a separately reviewed pack. Explicit device pins
must match a device reported by the selected runtime. Auto retains GPU only
after the shared CPU comparison passes, and failed GPU startup retries CPU.

Linux selection uses runtime-reported CUDA/Vulkan devices, including supported
Intel, AMD and NVIDIA GPUs/iGPUs. Hardware and usable host drivers determine
availability; vendor or card model names are not fixed in the selection policy.
Vulkan needs the corresponding host driver/device exposure, rather than CUDA.

The standard topology always requires asset-seed before production/model-setup,
including CPU, CUDA, Vulkan, torch and native Windows modes. Seed and model setup
run with networking disabled; application model consumers use verified local files
with HF/Transformers offline flags. Native Windows extracts the pinned OCI pack
and verifies it before executing any runtime binary. `compose.assets.yaml` is now
a compatibility overlay; selecting it manually is unnecessary.

The actual asset release is **BLOCKED**, with no invented license inventory or
OCI digest. Fresh setup fails explicitly until a complete reviewed pack is
published. See [controlled assembly and required real-model gates](../assets/README.md).
Production/kit CI promotion checks these identities and actual offline inference.

Upgrade managed kit files using the existing exporter `--upgrade` option. It
backs up managed templates and preserves deployment.env. Review the exporter's
asset-image/manifest display and mismatch warning; copy only the independently
reviewed release pins into the preserved operator environment. Never delete
volumes to fix missing assets. `make platform-assets` shows running image IDs and
verifies the active pinned pack. Roll back with matching image/kit/pins; retain
active/previous pack directories and existing index data.

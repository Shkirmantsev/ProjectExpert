# Apply embedding choices from the UI

The control page now applies the embedding binding and execution device when
**Apply model & device and build index** is pressed. Dropdown selection alone
changes nothing. The resulting background job reports completion or failure;
the page separately reports the live embedding execution mode.

The updated application and deployment kit are both required. The old immutable
application from PR #14 does not contain this feature. An old application with
new templates may still serve search but cannot provide the new UI behavior.
Use the matching new kit after publication, export it with `--upgrade`, retain
your private `deployment.env`, then run ordinary `make platform-start`.
No mandatory parameters or chat LLM are introduced.

The kit exports `runtime_supervisor.py`, `runtime-entrypoint.sh` and
`compose.ui-vulkan.yaml`. Setup provisions a stdlib-only Python bundle from the
pinned application into the model volume, excluding application packages. The
runtime images need no system Python installation. Fresh-device probing bypasses
the controller and works before setup. The supervisor
owns only the fixed llama-server child. Its internal API accepts device/fit
choices, authenticates using the existing embedding key, checks health and rolls
back failed launches. It does not expose a Docker socket, arbitrary shell commands,
model paths or a published host control port. A CPU-first Linux deployment can
switch to Vulkan when `/dev/dri` exists on the host; an unavailable GPU request
fails with guidance. CUDA needs the matching CUDA image/NVIDIA passthrough from
startup. Native Windows GPU host services remain managed by their host launcher;
the UI reports that limitation. In-process native Transformers uses the selected
supported device directly.

The model selector distinguishes the GGUF and native Transformers bindings of
one Gemma checkpoint. Native weights may need a separate download, and hardware
depends on the installed PyTorch build (CPU in the standard production image).
The UI offers installed bindings and limits native devices accordingly. Existing
canonical knowledge is retained; vectors remain isolated by embedding profile.

Explicit UI choices are saved under the target's ignored
`.project-intelligence-cache/runtime-selection.json` and take precedence over
deployment defaults. Remove that one override file only if you deliberately want
to return to deployment defaults; do not erase the cache. Application restart
reapplies the choice. Auto compares CPU and exposed GPU latency with the existing
fixed corpus and 1.10x speedup threshold. A GPU backend with CPU projector is shown
as **Hybrid**; this does not assert a measured GPU layer count.

`PI_UI_TOKEN` is an optional operator-chosen API bearer password. It is unset by
default for loopback deployment; there is no generated credential to find. Leave
the UI field empty when its message says authentication is not configured. If
enabled, obtain it from the operator's private environment/password manager. It
protects ProjectExpert REST/MCP/OpenAI-compatible access, including configuration,
and is distinct from an LLM provider key or signed knowledge approval token.
The UI never returns it and keeps a supplied token only in tab memory. See the
[kit instructions](../distribution/deployment/README.md) for private configuration.

## Verification evidence

Regression tests cover explicit GPU failure, child rollback, fixed arguments,
initial fit budget, Auto policy, restart persistence, model-factory/index wiring,
live status after restart, API authentication metadata and UI background jobs.
The browser test executes the actual shipped JavaScript with async job polling.

On the Linux verification host, an isolated pinned Vulkan b11515 runtime with
the existing cached Gemma Q8_0 weights switched CPU → Vulkan0 → CPU and returned
a real 768-dimensional runtime embedding (the application adapts it to its pinned
512-dimensional profile). Unauthorized control was rejected. The new application's
UI HTTP API applied Vulkan through a job, published Hybrid mode and retrieved
project evidence. The GPU choice survived an application restart whose environment
default was CPU. Auto measured CPU median 17.36 ms versus Vulkan median 29.00 ms
(0.60x speedup), correctly retaining CPU. These timings describe that host and
corpus only. Native model-factory switching was tested with controlled embeddings;
no additional native weights or external chat model were downloaded for the test.
The portable bundled-Python entrypoint subsequently passed the same real UI
CPU/Vulkan/Auto/CPU sequence. The optional CUDA image interpreter probe was stopped
after repeated registry-layer download retries; system Python is no longer required.

Local application verification uses the unchanged dependency closure from the
previous immutable production image with current `pi_platform` source overlaid in
a separately tagged image. It is local verification, not a newly published OCI
release. The ordinary Containerfile/publication workflow still builds the full
dependency closure for release. Physical Windows and NVIDIA inference are not
claimed by Linux Vulkan acceptance.

## Installed trade-analyzer verification — 2026-11-04

The target was safely upgraded with the matching local kit. Its immutable local
application ID is `sha256:af07a2be140c0d9ec9289826f4a68142d5fee5e738b88c02d20941198dea5510`;
kit ID is `sha256:a183b26043eb2746e475d0b16c2bc34b44027fd5986baae1a847920357ebaf46`.
These local IDs are not downloadable GHCR release digests. Export preserved
deployment.env, old-template backups, model/index/UI volumes and the exact
pre-existing Git staged diff. Ordinary `make platform-start` returned healthy.

Actual browser actions on port 8766 completed Vulkan → Hybrid and Auto → CPU.
The target Auto run measured CPU 22.92 ms versus Vulkan 30.26 ms (0.76x speedup).
The saved request is Auto; explicit Vulkan remains available. The page showed
completed jobs and correctly disabled its API-token input because authentication
was unconfigured. The pre-existing malformed target Python file remains an
isolated parse error; it is unrelated to runtime control.

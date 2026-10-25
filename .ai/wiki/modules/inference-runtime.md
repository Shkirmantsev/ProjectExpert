---
id: modules.inference-runtime
title: Inference runtime
kind: modules
status: active
summary: Portable inference runtime policy that probes llama.cpp devices, selects a usable CUDA, Vulkan or CPU backend and downgrades to the validated CPU profile when no GPU is available.
sourceRefs:
  - pi_platform/core/inference/backend.py
  - pi_platform/core/inference/device_probe.py
  - pi_platform/core/inference/profile.py
  - pi_platform/core/inference/launch.py
  - pi_platform/cli/inference.py
  - openspec/changes/consolidate-embeddinggemma2-and-autoconfigure-inference/specs/portable-inference-runtime/spec.md
maintenance:
  mode: authored
related:
  - adr.0029-portable-model-runtime-and-oci-kit
  - interfaces.one-command-ux
---

# Inference runtime

One Python-owned place for backend discovery, device selection, the
launch plan and the degradation behaviour. The package
`pi_platform/core/inference/` holds the policy; the Bash and
PowerShell deployment launchers only collect probe evidence and
apply the decision produced here.

## Package

- `backend.py` — backend vocabulary and probe value types.
  `BACKEND_PREFERENCE_ORDER` fixes the candidate order
  `cuda -> vulkan -> cpu`; the CPU backend is always available
  and is the final fallback; a GPU is an optimisation, never a
  startup prerequisite. Pure data: no I/O, no subprocesses.
- `device_probe.py` — parses and runs `llama-server
  --list-devices`. `parse_device_list` turns the report into
  `DeviceInfo` records (backend from the name prefix, software
  rasteriser detection, integrated-GPU flag, reported free
  memory or `None` when not reported — never invented).
  `probe_binary` runs the probe as a bounded subprocess and
  reports timeout or launch failure through a
  `BackendCandidate` instead of raising.
- `profile.py` — `select_profile(...)`, the pure selection
  policy (no I/O, unit-testable without hardware).
- `launch.py` — `build_server_argv(...)` builds the explicit
  `llama-server` argument vector; `compose_device_fragment(...)`
  returns the `PI_ACCELERATOR` / `PI_GPU_DEVICE` / `PI_FIT_TARGET`
  Compose environment fragment for the decided profile.

## CLI

`python -m pi_platform.cli inference` (`pi_platform/cli/inference.py`)
exposes three subcommands:

- `inference plan` — reads probe evidence
  (`--evidence-b64`, `--evidence <path>` or stdin), computes the
  profile and prints exactly one decision JSON object on stdout
  (backend, device, fit target, rejected candidates,
  `server_args`, `compose`) so the deployment launchers can parse
  it directly;
- `inference doctor` — the full diagnostic report: environment,
  model files with checksums, the evidence, the decision and the
  rejected candidates;
- `inference status` — the status of the configured runtime
  endpoint.

## Selection policy

- Candidates are evaluated in `cuda -> vulkan -> cpu` order
  (`prefer` order; a non-preferred backend is evaluated last).
- A candidate is selected only when the runtime's own
  `--list-devices` report contains a usable device of that
  backend. A candidate is rejected — with the reason recorded in
  `profile.rejected` — when the probe failed, when no device was
  reported, when every device of the backend is a software
  rasteriser, when the backend is not preferred, or when only
  integrated devices remain and they are not allowed.
- A software rasteriser (lavapipe, SwiftShader, llvmpipe,
  softpipe, …) is never selected.
- An unavailable or unusable GPU is a DOWNGRADE to the validated
  CPU profile (`reason`: "no candidate validated; cpu baseline is
  the fallback"), never a startup failure. The CPU baseline
  succeeds with no devices at all, because CPU-only execution
  deliberately disables device use.
- A GPU that works but is SLOWER than the CPU baseline is also
  rejected. The launcher measures the CPU baseline and every
  validated GPU candidate with the same fixed corpus
  (`inference benchmark`) and a GPU candidate is only selected when
  it is at least 1.10x faster. The verification host measured a
  0.72x speed-up for its integrated Vulkan GPU, so the CPU profile
  was selected there; the Vulkan profile remains available and is
  used when the operator selects it explicitly.
- The device memory the runtime reports is the FREE figure
  (`(32334 MiB, 30768 MiB free)`), never the total. The fit budget
  is computed from the free memory only, because a budget derived
  from the total would promise memory the runtime cannot use.

## Launch contract

- The multimodal projector always stays on the CPU: the argument
  vector ends with `--no-mmproj-offload` exactly once.
- Runtime flags are passed as an EXPLICIT argument vector, not
  through `LLAMA_ARG_*` environment variables, because llama.cpp's
  environment names differ from its flag names and a wrong name is
  silently ignored: `--batch-size` is `LLAMA_ARG_BATCH`,
  `--ubatch-size` is `LLAMA_ARG_UBATCH`, `--parallel` is
  `LLAMA_ARG_N_PARALLEL`.
- For a GPU backend the vector carries `--device <name> --fit on
  --fit-target <mib>`; for the CPU backend `--device none`.

## Related

- [`adr.0029-portable-model-runtime-and-oci-kit`](../adr/0029-portable-model-runtime-and-oci-kit.md)
- [`interfaces.one-command-ux`](../interfaces/one-command-ux.md)
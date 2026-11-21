# Windows native NVIDIA CUDA and Intel Vulkan recovery

This repair is for the separate Windows work PC. The Linux development PC and
its running installation do not need to change. Source/software validation does
not certify physical Windows GPU operation or speed.

## What failed

The primary offline pack contains Vulkan, including the native path used by
Intel integrated graphics. It intentionally excludes NVIDIA CUDA DLLs. The old
launcher treated that inventory as the full list of available host runtimes and
skipped native CUDA before probing it. Rancher Desktop without NVIDIA container
passthrough therefore reached CPU even when the Windows NVIDIA driver worked.

The launcher now resolves an optional, independently verified native CUDA pack.
The order is container CUDA, native CUDA, native Vulkan, CPU for `auto`. Explicit
`cuda` tries both CUDA transports and then CPU; it does not choose Vulkan.
Explicit `vulkan` uses the native Vulkan runtime; `PI_GPU_DEVICE=Vulkan1`, for
example, selects an Intel iGPU only if the actual probe reports that device.
There is no required Docker engine, driver or CUDA toolkit replacement.

## Obtain the matching kit

Use a newly built/published application image and its matching exported kit.
Restarting an older pinned image cannot install source repairs. Existing
`deployment.env` is preserved on kit upgrade; explicit `PI_IMAGE` overrides still
win. A fresh verified kit writes its immutable application image into the new
environment file; the workspace helper and Windows wrapper also read the verified
release identity when the entry is absent. Source-only/unpublished kits require
an explicit compatible image and cannot invent an OCI digest.

## Offline CUDA import on the Windows PC

The two previously obtained archives can be reused **only** if they match:

| Archive | SHA256 |
|---|---|
| `llama-b11515-bin-win-cuda-12.4-x64.zip` | `9381b20187aef342cf45b8f1a8605e66c244fc0a33176a2406655221522d992e` |
| `cudart-llama-bin-win-cuda-12.4-x64.zip` | `8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6` |

No work-PC download from GitHub/Hugging Face, TLS bypass or global DLL copying
occurs. From the new `.project-intelligence-deploy` directory, inspect local
archives into a **new** private directory outside Git (example paths are chosen
by the operator, not project source paths):

```powershell
.\native-cuda.ps1 -Action inspect -Source 'C:\ApprovedAssets\cuda-archives' -Destination 'C:\ApprovedAssets\cuda-candidate'
```

This uses the existing application image with `--network none`. The output is a
**blocked candidate**, not permission to execute. An independent operator/license
reviewer must inspect the exact archive inventory and actual licenses:

1. Set `licenses/operator-review.json` to `approved: true`,
   `scope: operator-local` and a meaningful `review_id` only after real approval.
2. In `manifest.json`, set the actual per-file `license` expressions, retain
   exact archive-member provenance/revision, update the review file's SHA256,
   and set `release_status: verified`. All files reference the inventoried
   `licenses/operator-review.json` as `license_evidence`.
3. Compute the SHA256 of the final manifest bytes. This independent pin is
   required for every installation/start. Editing any bytes invalidates it.

Do not label NVIDIA DLLs MIT because llama.cpp is MIT. There is no public CUDA
companion approved in this repository; the default asset review is unchanged.

When the reviewed pack and its manifest hash are supplied by your organization,
install and select it in one command. No deployment.env edits are required.

```powershell
.\native-cuda.ps1 -Action install -Source 'C:\ApprovedAssets\cuda-candidate' -ManifestSha256 $nativeManifest
```

The equivalent Make command is `make platform-gpu-install GPU=cuda GPU_PACK=... GPU_PACK_SHA256=...`.
For the bundled Vulkan runtime use `./setup-windows-accelerator.ps1 -Backend vulkan -AssetsOnly`.
An explicit `PI_NATIVE_CUDA_SOURCE` setting overrides the installed selection.

```powershell
$nativeManifest = (Get-FileHash 'C:\ApprovedAssets\cuda-candidate\manifest.json' -Algorithm SHA256).Hash.ToLowerInvariant()
.\native-cuda.ps1 -Action verify -Source 'C:\ApprovedAssets\cuda-candidate' -ManifestSha256 $nativeManifest
$env:PI_NATIVE_CUDA_SOURCE = 'operator-local'
$env:PI_NATIVE_CUDA_LOCAL_ROOT = 'C:\ApprovedAssets\cuda-candidate'
$env:PI_NATIVE_CUDA_MANIFEST_SHA256 = $nativeManifest
$env:PI_ACCELERATOR = 'cuda'
# Set only a device actually reported by the native runtime:
$env:PI_GPU_DEVICE = 'CUDA0'
$env:PI_ACCELERATOR_STRICT = '1'  # optional: fail instead of accepting CPU fallback
.\compose.ps1 up -d
```

These non-secret preferences may be placed in the private installed
`deployment.env` for subsequent starts; do not commit machine paths or credentials.
The installed verified tree is `accelerator/native-cuda/<manifest SHA256>/`.
It is isolated from Vulkan and reverified on reuse; old trees/caches are retained.
The candidate binds to the **exact primary asset manifest**. A different primary
release requires a newly reviewed matching manifest, rather than bypassing checks.

A future independently approved OCI companion uses
`PI_NATIVE_CUDA_SOURCE=reviewed-oci`, immutable `PI_NATIVE_CUDA_IMAGE` and
`PI_NATIVE_CUDA_MANIFEST_SHA256`. Pre-pull the approved image using ordinary
verified registry transport; the resolver uses `create --pull never` and never
adds a companion download to normal CPU/Vulkan startup.

## Serving, selection and performance

A successful device list alone is insufficient. The native server must load the
pinned model/projector and expected alias. Before activating production, a real
authenticated container-to-host request must return a finite 768-dimensional
embedding. Failure remains an explicit diagnostic, never GPU success.

Native serving uses the address verified from inside the application network
and the configured port (8769 by default). The managed host runtime binds beyond
loopback so Docker/WSL can reach it and requires the private API key file. Retain
Windows Firewall restrictions for the required Docker/WSL network; the launcher
does not change firewall rules. DLL resolution uses the isolated verified runtime
directory and Windows system directories, without relying on a host CUDA toolkit.

The Q8 projector stays on CPU; the shared policy retains GPU fit/memory limits.
Explicit CUDA/Vulkan is not rejected just because CPU benchmarks faster. `auto`
retains the existing same-corpus speed comparison and may legitimately choose
CPU. Select an explicit backend to distinguish availability from that optimization.

Explicit CPU skips native probes and copying the multi-GB offline pack onto the
host. Optional CUDA verification streams archive/member hashes with bounded
memory; installed assets are reused without repeated extraction. Source-parser
parallelism, batching, private caches and embedding identities are unchanged.
A transport change alone does not force reindexing. No speedup on MX550/Intel is
claimed until measured on that PC.

## Diagnostics and work-PC acceptance

Read private `accelerator/plan.json`, `probes.json`, `container-probe.json`,
`devices-cuda.txt`, `devices-vulkan.txt` and runtime logs. New plans retain the old
fields and add requested/selected backend, transport, rejection details, asset
identities and successful embedding smoke. Do not publish raw private logs.

Missing pack, bad pin/approval, missing selected device, probe timeout/nonzero
exit, server/model failure and failed serving-path smoke are distinct. Container
errors distinguish unavailable GPU, interrupted asset transfer and disconnected
Docker engine. No automatic destructive retry or cache cleanup is used.

Run the packaged path under **Windows PowerShell 5.1 and PowerShell 7**:

1. Check `nvidia-smi` and the actual Rancher Docker engine without changing them.
2. Start explicit CUDA with the reviewed pack. Check the real CUDA0/MX550 probe,
   the verified executable's PID/path, `plan.backend=cuda`,
   `transport=native-windows` and `embeddingSmoke.ok=true`.
3. Index a sanitized small project, retrieve through MCP, warm restart and run
   incremental indexing. Record startup, embedding latency/throughput, memory and
   cache hits. Do not upload confidential corporate source to CI.
4. Stop via `stop.ps1`; repeat explicit Vulkan with the actual Intel device, then
   CPU. Existing local knowledge must remain available. CPU without CUDA source
   must not copy/probe optional native runtimes.
5. Repeat offline after approved pulls are cached. No model/runtime web downloads
   should occur. Strict missing-GPU mode must fail before production/index startup.

These hardware checks are **NOT RUN** on the Linux development machine. The
shared Windows CI acceptance is software/fixture evidence, not MX550 certification.

## Rollback

Stop only the kit-owned native process with `stop.ps1`. Restore the prior backed-up
kit/image and operator environment, or select `PI_ACCELERATOR=cpu` / verified
`vulkan` and disable the optional CUDA source. Retain all model, workspace,
SQLite/index volumes, cache directories and Git knowledge. Never use `down -v`,
volume prune, a TLS bypass or driver replacement as recovery steps.

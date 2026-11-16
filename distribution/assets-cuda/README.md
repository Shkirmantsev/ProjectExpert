# Optional Windows native CUDA companion

The default model/Docling/Vulkan asset pack remains unchanged. No CUDA companion
image or NVIDIA DLL redistribution is approved by this source tree. The blocked
release record is deliberate; do not invent an image digest or change NVIDIA
binaries to MIT. Operator-local use also needs the operator's actual policy and
license review.

`pi_platform.deployment.native_runtime_assets` implements offline inspection,
verification and atomic installation independently of the full model pack. The
Windows wrapper is `native-cuda.ps1`; the complete procedure is in
[the Windows recovery guide](../deployment/WINDOWS_NATIVE_GPU_RECOVERY.md).

Inspection consumes only the two exact archives already pinned by
`distribution/deployment/accelerator-lock.json`. It produces a blocked candidate
with every extracted file, SHA256 and archive-member provenance. The independent
review must cover each file's actual license, including NVIDIA components, and
set the scoped review evidence before the manifest can become verified.

A reviewed-OCI deployment must additionally use an immutable
`ghcr.io/shkirmantsev/project-intelligence-native-cuda@sha256:<digest>` and a
separate exact manifest pin. Its payload is rooted at
`/opt/projectexpert-native-cuda/`; the manifest uses the same schema and exact
primary-manifest binding as operator-local imports. Review evidence must declare
`scope: redistribution`, rather than `operator-local`.

Public materialization/publication automation is deferred until an actual binary
inventory and independent redistribution review exist. The implemented local
import path needs no public CUDA image and does not change ordinary CPU/Vulkan
asset downloads. Neither fixture tests nor a passing hash check grant a license.

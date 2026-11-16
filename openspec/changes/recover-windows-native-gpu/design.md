# Design

Keep the default model/Docling/Vulkan pack unchanged. A standalone CUDA pack is
bound to the exact primary manifest and pinned llama.cpp runtime. An offline
candidate builder expands only exact pinned archives into an isolated tree and
records all files/provenance. Candidates remain blocked until a human reviews
per-file licenses and scope. An independent verifier checks the complete inventory,
archive-derived binary closure, Windows path semantics and scoped approval before
atomic installation under accelerator/native-cuda/<manifest hash>.

The Windows host invokes the verifier inside the existing application container
with networking denied, then probes/starts the verified host executable. Container
CUDA stays first; native CUDA and Vulkan follow, with CPU fallback. Explicit CUDA
never silently selects Vulkan. Strict mode can reject unavailable explicit GPUs.
A process helper uses System.Diagnostics.Process, async pipe reads and bounded
cleanup. It does not depend on Start-Process ExitCode behavior.

Private keys, cache identities, source indexing and Git export are untouched.
No toolkit/driver installation, TLS bypass, remote download, cache deletion or
Linux live deployment update. Public companion publication stays blocked pending
actual independent binary/license review; local inspection/import is complete
without a new public image. Hardware correctness and throughput cannot be inferred
from synthetic fixture success.

## Implementation scope refinement

The working delivery is the operator-local path plus an independently verified
OCI resolver. No public CUDA build/publisher is enabled before an actual reviewed
binary inventory exists. P1 automatic transient retries/seed re-observation are
deferred; categories are recorded without retrying integrity or approval failures.
See verification.md for software proof and separate Windows/hardware gates.

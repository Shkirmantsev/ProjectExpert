# Recover Windows native GPU inference

## Why
The standard reviewed assets include Vulkan only. Native CUDA is skipped when
container GPU passthrough is absent, despite exact CUDA archive pins already
existing. Windows PowerShell process probes and first-start image resolution also
have independently reproducible software gaps.

## What changes
Add an optional separately verified native CUDA pack, including offline inspection
and operator-local import. Resolve CUDA independently of the primary Vulkan pack.
Use one bounded native probe helper under PS5.1/7. Preserve explicit selections,
Vulkan/iGPU, CPU, existing indexes and host drivers. Bind fresh image configuration
to the kit release, and gate publication on the complete Windows launcher suite.

## Limits
No changes to this Linux installation or the remote work PC. No public NVIDIA
binary redistribution approval is granted. Actual Windows NVIDIA/iGPU inference
and performance remain physical acceptance gates, distinct from fixture tests.

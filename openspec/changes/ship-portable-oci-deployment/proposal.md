# Portable production OCI deployment

## Why
The dev publisher currently tags a model-free core image as dev. Production
publication is separate, license-blocked, and has no standalone deployment kit.
Windows and Linux users need automatic embeddings without a CUDA prerequisite.

## What changes
Publish the verified production image and a matching deployment kit on dev and
development and main pushes. Ship Compose, safe defaults, product-only Make targets and
Linux/Windows launchers. Persist automatically downloaded embedding weights.
Keep exact dependency review fail-closed; no global license-policy expansion.

## Impact
Affects one-click distribution and release configuration. Existing source and
core profiles remain available. Wiki: interfaces.one-command-ux,
modules.release-gate. CUDA/Vulkan acceleration must not be claimed from CPU proof.

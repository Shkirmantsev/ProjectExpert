# Tasks

- [x] Implement standalone deployment bundle and preserve operator files.
- [x] Configure dev production publication and matching digest-bound kit.
- [x] Verify automatic model startup, readiness and restart in a real container.
- [x] Resolve exact production dependency review without a global policy bypass.
- [ ] Check Linux and Windows launcher behavior and hardware support boundaries.
- [x] Update Wiki and installation guidance; run focused tests and harness check.

- [x] Add main publication and retained commit tags.
- [x] Add pinned Qwen GGUF runtime and CPU/Vulkan/CUDA selection.
- [x] Restore Gemma vision and pass image assets to the real encoder.
- [ ] Verify physical Vulkan/CUDA hardware and Windows Docker Desktop.

## Verification boundary

Real CPU production startup/search/restart and Gemma image inference passed.
Real Qwen GGUF inference passed on CPU in the pinned Vulkan runtime image.
The exact dependency review is approved. Physical GPU, Windows and remote
publication remain unverified; this change is not adopted as completed. The locally verified CPU asset setup
and exact license-review contracts have been synchronized into current specs;
this does not adopt the pending cross-platform acceptance claims.

- [x] Preserve Gemma/Qwen selection across CPU/Vulkan/CUDA deployment modes.
- [x] Add pinned Gemma GGUF projector setup and pixel-sensitive image inference.
- [x] Verify explicit Qwen CPU and optional GGUF CPU configuration.

- [x] Reconcile Gemma image loading and effective model status in current specifications.
- [x] Document runtime boundaries and trade-offs in ADR 0029 and deployment architecture.
- [x] Update README, Wiki navigation and deployment profile distinctions.

- [x] Correct CI-discovered owned SQLite handles, ANN empty-generation dimensions, optional dependency assumptions and Windows test exit/path handling.
- [ ] Confirm corrected PR checks on GitHub, including previously blocked container jobs.

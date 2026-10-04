# Security notes

- This sidecar is a **control plane only**. It has no project mount, binding DB, upload endpoint, project-file API, or second Hermes runtime.
- Bind the sidecar only to the remote node's Tailscale IP and require `HERMES_SIDECAR_TOKEN` on every HTTP route.
- The sidecar talks only to the existing Hermes API on loopback (`http://127.0.0.1:8642`).
- `HERMES_API_KEY` is copied from the existing worker profile without printing it; do not commit `.env`.
- Project access remains the responsibility of the native `hermes-tailscale-worker` SSH backend and the dedicated ACL-limited `hermes-worker` account on the main machine. The sidecar additionally canonicalizes every requested root and enforces `HERMES_ALLOWED_PROJECT_ROOTS` before forwarding it.
- `hermes_run` omits a `/v1/runs` model override so the worker profile's provider/model configuration cannot be accidentally replaced by the public profile/model identity.
- A fresh Hermes session is created by default. Reuse a returned `session_id` only for deliberate continuation.
- Approval-paused runs are never auto-approved. `hermes_approve` requires an explicit caller action and validates the allowed choice.

# Enable UI embedding runtime control

## Why

UI selections currently persist but cannot change a managed sidecar, while deployment environment defaults override them on restart. Make supported model/device selections apply before indexing, persist explicit operator intent, expose capabilities and verified status, and explain optional API authentication. No Docker socket or host-command execution is granted to the UI.

## What Changes

- Apply supported model bindings and managed child devices through observable jobs.
- Persist explicit UI choices independently of deployment defaults.
- Publish observed runtime mode, available bindings and optional API token status.
- Ship an internal authenticated child supervisor with a stdlib-only Python bundle.
- Verify real Vulkan operation, restart persistence and measured Auto selection.

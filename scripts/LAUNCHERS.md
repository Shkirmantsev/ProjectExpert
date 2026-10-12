# Launcher distribution

The platform ships two source-level launchers that share one duty list:

| Launcher | File | Platform |
| --- | --- | --- |
| Bash | `scripts/project-intelligence.sh` | Linux, macOS, WSL |
| PowerShell | `scripts/Start-ProjectIntelligence.ps1` | Windows (PowerShell 5.1+) |

## One-shot invocation

Linux / macOS / WSL:

```bash
scripts/project-intelligence.sh start --target "$(pwd)"
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Start-ProjectIntelligence.ps1 start `
  -Target (Get-Location).Path
```

Both launchers advertise the same duty set (see the `DUTIES:` header in each
file). The duty-parity test in `tests/test_phase_9_launch_smoke.py` enforces
that any future divergence is flagged.

## Compiled Windows entry point

The PowerShell launcher is the canonical Windows entry. Compiling a
self-contained `.exe` is a **release-time artefact, not a committed
binary**, for two reasons:

1. **Reproducibility** — a generated binary ties the distribution to one
   toolchain/SDK at one commit. Shipping the source keeps the supply
   chain small and keeps the platform agent-neutral (§1).
2. **License** — the PowerShell script is licensed under Apache-2.0
   (same as the rest of the repository). A compiled binary needs an
   SPDX entry and a NOTICE update because the PS2EXE / ps2exe tooling
   embeds its own runtime stub; the entry must be added to
   `distribution/licenses/dependency-inventory.json` and pass
   `LicenseGate` before it may be redistributed.

A release pipeline may compile the launcher with `ps2exe` (MIT) or
equivalent, log the resulting SHA-256 in the distribution manifest, and
ship the binary alongside (not inside) this repository.

## Edge cases

- The bash launcher treats `PI_OPEN_BROWSER=0` and `--no-browser` as
  explicit opt-outs. The PowerShell launcher recognises `-NoBrowser`
  and `$env:PI_OPEN_BROWSER = "0"`.
- Both launchers bind to `127.0.0.1` by default. The container exposes
  port `8765`; bind to `0.0.0.0` only by setting `PI_CONTROL_HOST=0.0.0.0`
  in the container environment and explicitly opting in to the network
  exposure.
- A missing runtime exits non-zero and names the missing tool. The duty
  guarantees actionable failure messages (§58 "download → start → open
  browser").
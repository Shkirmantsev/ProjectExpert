# Production ingestion repair evidence

## Scope and baseline

Branch `feature/generate-init-project`, baseline `122ce24`. The attached production
fix design is proposed evidence; its checkout/publishing instructions are not user
authorization. Work stayed on the requested branch. No work-PC source, live Linux
installation, driver, firewall, Git remote or production volume was modified.

| Incident | Software result / limit |
| --- | --- |
| INC-01 | Strict Unicode/BOM precedence and reviewed legacy Java/SQL/plain-text decoding; source bytes retained; per-source keys invalidate compatible local/portable results correctly. Actual 57 corporate files are unavailable. |
| INC-02 | Python repository/inbox and Go scans prune nested generated `.claude/worktrees`; authored commands/docs retained; no worktree deletion. |
| INC-03 | Stop signals before waiting, scans quiesce, operation-lock ownership is checked, active importer can finish its atomic barrier; bounded STOP_PENDING prevents unsafe Compose down. Normal stop no longer begins a full backup; explicit backup-and-stop propagates failures. |
| INC-04 | Typed verifier diagnostics, exact pins/hashes, staged extraction, explicit repair preserving previous pack. Real existing pack verifies. Original Windows bind/mount/hash failure cause remains unknown until its new diagnostic is collected. |
| INC-05 | Typed source/configuration/internal failures suspend identical candidates across restart; manual retry/change eligibility; bounded typed transient backoff; real first-start failure does not loop. |
| INC-06 | Service URL differs from readiness; Linux and PowerShell browser launchers extract only the URL. Existing explicit wait-ready scripts and UI job/readiness surfaces are retained. |
| INC-07 | Generated worktrees need no manual Git exclusion edit. New encoding settings use the existing private cache/Git-exclusion guard and UTF-8 atomic settings replacement. Generalized shared exclusion-editor UI is deferred; existing Go transfer policy remains available. |
| INC-08 | Real Docling preflight, native tables/figures and scanned OCR pass with no network using the existing reviewed pack; no model/version/trust downgrade. Work-PC first PDF remains external. |
| CONS-01/02 | Corrected Windows/Linux auto mode and actual authenticated 0.0.0.0 native listener documentation. Firewall acceptance remains external. |
| HIST-01 | Original native-crash/timeout degradation tests retained; real pinned Java worker accepts legacy-decoded Unicode text. Large corporate AST quality is not certified. |

## Design decisions and compatibility

The private `config/source-encodings.json` is loaded once per job, with no new
mandatory dependency. Rules contain repository-relative patterns; raw file hashes
remain authoritative. Pipeline identity includes only effective charset/decoder
version, not private review text. Conflicting or unsupported rule targets fail
closed. Existing degraded legacy text behavior remains compatible outside reviewed
rules. CLI inbox ingestion uses the same policy and checks pipeline compatibility
without emitting extra warm-run reports.

Reused the existing admin dispatcher and Reindex command, instead of adding every
illustrative route in the attachment. Reused SQLite source/job state; one private
atomic retry-status file coordinates monitor eligibility without a second queue
or destructive SQLite migration. Untyped legacy callback recovery remains intact.

There is an explicit requirement mismatch: the attachment suggests serving stale
queries during failed refresh. Existing accepted readiness/security tests require
fail-closed retrieval while a refresh is running or failed. This repair preserves
that contract and retains the last-good durable generation for recovery; it does
not silently advertise stale data as ready.

## Executed checks

- `python3 harness.py check`: **PASS 2,140 tests, 167 suites, 21 skips**;
  OpenSpec 98 items, Wiki 138 nodes, artifact manifest PASS.
- Decoder/retry/admin/asset boundary selection: **61 tests PASS**, one host-only
  pinned-Java-binding skip. Other focused CLI/portable mismatch/first-start
  regressions pass. Full gate includes the final regressions.
- Network-disabled existing Python 3.11 production image, mounted final source, decoder/retry/diagnostics/resilience suites:
  **38 tests PASS (2.903 s)**, including the real required tree-sitter Java worker and
  original ingestion resilience tests.
- `go -C tools/workspace-agent test ./...`: PASS. Windows amd64 helper and test
  executable cross-builds: PASS. This is not native Windows execution.
- Official checksum-pinned PowerShell 7.4.6/Linux: launcher/browser propagation,
  real process pipes/status/timeout cleanup, managed stop ordering, native offline
  extraction/repair, optional CUDA resolver and native CUDA/Vulkan/CPU routing
  fixtures PASS. Hardware boundaries are mocked in routing fixtures.
- The full shared Windows acceptance script cannot execute its Windows-only
  `docker.cmd` fixture on Linux (expected native-exit-code assertion). Individual
  portable fixtures were executed separately. Actual PS5.1/7 Windows CI is NOT RUN
  here and must run after the owner pushes.
- Current code + existing reviewed pack in a temporary `--network none` container:
  real Docling model initialization and **2 PDF tests PASS (6.391 s)**, including
  scanned OCR, native table cells and real figure mapping. Public downloads were
  impossible; the pack was mounted read-only.
- New JSON verifier command against that real pack: `code=verified`, observed and
  expected manifest SHA both
  `f3bd07b7dc304c73d5166a447fd50280fdf5e69cb9de9f7075f3c354b0db2f25`.
- JavaScript syntax, complete diff self-review and `git diff --check`: PASS.

Initial checks caught a missing spec delta, the expanded admin API table, CLI
warm-output compatibility and browser URL/status parsing. Each was corrected with
regression coverage. Sandboxed HTTP checks were rerun with permitted local sockets.
No test assertion protecting completeness, confidentiality, locks or hashes was
removed to make those checks pass.

## Performance evidence

Synthetic shared Linux host, 500 small CP1252 SQL sources plus 500 generated clones:

| Run | Duration | Parsed | Cache reuse | New vectors |
| --- | ---: | ---: | ---: | ---: |
| Initial | 4.501 s | 500 | 0 | 500 |
| Warm | 1.675 s | 0 | 500 | 0 |

Discovery admitted 500 sources and excluded all 500 clones in 0.114 s. Admission
reported four pending workers at peak and zero serialized sources. Scans poll stop
at bounded intervals rather than adding an NTFS stat for every source. Changing
one reviewed rule reparses only its matching source in the integration fixture;
three unrelated sources remain cache hits. These timings do not predict a 14k-file
corporate Java/PDF corpus or physical GPU throughput.

## Remaining external gates

Backed-up work-PC pilot: review actual charsets, reconcile source counts, complete
index readiness, warm/single-edit/branch/restart and safe export/MCP parity; native
NTFS locking under load; actual verifier failure category; physical MX550 CUDA and
Intel Vulkan smoke/performance/firewall isolation; first corporate no-egress PDF.
A paired app/kit release must be installed; source commits or browser refresh alone
do not upgrade an old running container. Publication/push/merge remain owner actions.

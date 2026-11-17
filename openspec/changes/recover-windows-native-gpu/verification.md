# Recovery verification — 2026-11-16

Implemented on the existing `feature/generate-init-project` branch, starting at
`3ce834f`. The attached RFC audited another commit; its branch/handoff instructions
were treated as design material, not authorization to switch branches or deploy.
The current Linux host is the development PC, not the separate Windows work PC.

## PASS

- `python3 harness.py check`: **2,116 tests / 163 suites / 20 skips**;
  OpenSpec **97/97**, Wiki **138 documents**, artifact manifest **1,626 files**.
  Existing graph50k build **3.8s**, total with cleanup **5.0s**.
- `GOCACHE=/tmp/projectexpert-go-cache go -C tools/workspace-agent test ./...`:
  PASS. Native Windows amd64 helper cross-build: PASS.
- New offline CUDA integrity/import suite: **13 PASS**. Includes blocked approval,
  main/runtime binding, archive pins, binary closure substitution, extra/missing/
  corrupt files, evidence, Windows aliases/case/ADS, symlinks/hardlinks, expansion
  bounds and preservation of prior installed data.
- Official temporary PowerShell **7.4.6 on Linux**, checksum-verified under `/tmp`:
  parser PASS; real process argv/Unicode-space filename, integer0/23, simultaneous
  large stdout/stderr, immediate stderr-only, timeout cleanup, missing executable
  and caller preference tests PASS. No Linux package/system installation changed.
- PowerShell7 controlled-boundary suites PASS: actual native setup routing,
  optional resolver, offline extraction/verification, container CUDA preference/
  fallback/strict, generic deployment launchers. Hardware and Docker boundaries
  in these suites are mocked. The same shared entry point is now required by both
  Windows asset acceptance and production promotion, under **PS5.1 and PS7**.
- Red-to-green regressions: missing release image on fresh start; preserved kit
  override; Compose child image equals helper/release image and restores caller
  environment; explicit CPU avoids host-native copy/probe; wrong/missing CUDA
  remains precise CPU/strict fallback; parent-case ZIP collision rejected.
- Isolated application packaging smoke, `--network none`: the packaged b11515
  runtime lock resolves with both pinned CUDA archives; **13 verifier tests PASS**
  under Python3.11. Test image (cached dependencies plus source/lock overlay):
  `sha256:7763cdd9dca33fdd54ed57016fb9ac3fc05dd1650c76890f25ecf2386e3a8032`.
  This is a local software test image, not a published release or live upgrade.
- Streaming integrity experiment with a **64MiB synthetic binary closure**:
  inspection0.343s, verification0.184s, atomic installation0.653s on Linux. This is
  asset-processing overhead, not MX550/Intel inference or full-pack benchmarking.
- Focused Python deployment suites: **47 PASS**; subsequent native security
  expansions are covered by the final13 native tests and the full gate.
- Final diff whitespace checks PASS; final manifest after adding this evidence
  document: **1,627 files PASS**. No push, merge, driver/firewall change,
  confidential-project upload, runtime data deletion or live installation change.

## NOT RUN / external acceptance

- Real Windows PowerShell5.1 execution, NVIDIA MX550 / Intel Vulkan inference,
  actual Rancher Docker-to-host routing, model memory fit and hardware throughput.
  The shipped operator guide lists the exact acceptance procedure. Source fixtures
  must not be reported as passing physical GPU acceptance.
- Fresh hosted Windows/CodeQL runs: require owner push; no results fabricated.
- Public CUDA companion publication and independent per-file redistribution
  approval: **blocked**, deliberately. The default approved assets remain Vulkan
  only. Operator-local approval is a separate explicit review, not granted by
  successful hashing. No actual CUDA archive/binary is committed or distributed.

## Design scope and deferred work

The complete supported path delivered now is offline inspection, independent
review, local installation/resolution and native serving activation. A future
reviewed OCI companion is supported by the resolver/verifier but has no fabricated
image pin, approved inventory or automatic publisher. Public build/promotion stays
deferred until its real review and hardware gates can be satisfied.

Transport errors have structured categories; automatic retry/seed re-observation
from the RFC's P1 reliability phase is deferred. Existing cache-preserving behavior
remains; no broad retry of integrity, approval or authentication failures was added.
Unreproduced Java/HTML/parser backlog items are not folded into this GPU repair.

Local source commits: `88c75e2` foundation image identity; `e14d970` verified
native GPU/runtime/CI recovery. Documentation and final task evidence are committed
separately. The recovery OpenSpec change remains active; accepted current specs
are not silently rewritten or falsely marked hardware-certified.

## PR28 Windows follow-up — 2026-11-17

The pushed candidate `c4fd4e7` was tested as PR merge `479515d8`. All six full-Windows and six Windows-unit logs from
runs43974331842,43974331890 and43974331728 showed the same causes across Windows
Python3.11/3.13: full harness stopped at the fresh-kit CRLF fixture, while unit
discovery additionally reached the ZIP-backslash case. Linux checks passed.

The CRLF fixture used text mode with an already explicit CRLF, so Windows created
CRCRLF before the exporter ran. It now writes/asserts exact bytes. Exporter
preservation semantics are unchanged. The ZIP fixture also accidentally invoked
host normalization in `ZipInfo`; it now stores the intended hostile member name.
The verifier validates `orig_filename` before Python normalizes backslashes or
truncates NUL, retaining strict rejection on every supported host.

Negative raw-name tests were red against the prior validator, including simulated
Windows separators on Linux. The patched native pack suite has15 passing tests,
including ordinary forward-slash names accepted under both host separators.
The exporter test also passes with Windows text translation forced on Linux.
There are no skips or relaxed security expectations added by this follow-up.

The **original** [hosted Windows launcher job133674291292](https://github.com/Shkirmantsev/ProjectExpert/actions/runs/43974331890/job/133674291292) passed both PS5.1 and7
before these Python fixes. This is software/process/fixture evidence, not physical
MX550/Intel inference. Fresh hosted Python results still require the owner's push;
no re-run of unchanged failing commits or remote branch mutation is performed.

Supplemental Python3.11 container run with the patched module and test files
mounted read-only, `--network none`:15 native runtime tests PASS. No application
image publication, live service restart or dependency modification was needed.

Final local follow-up gate: `python3 harness.py check` **PASS:2,118 tests in163
suites,20 skips**; OpenSpec97/97, Wiki138 documents, artifact manifest1,627 files.
The full gate includes the two new raw-name/canonical-name regression tests.
`git diff --check` and final manifest verification PASS. Fresh Windows hosted
Python3.11/3.13 execution after this repair is NOT RUN until owner push; the old
jobs are not relabeled as successful. Changes are committed locally only.

## Remaining PR28 Windows unit acquisition race — 2026-11-17

After30059aa, run43978086547 passed full-Windows3.11/3.13, Windows-unit3.13,
Linux checks and shared PS5.1/7 launcher acceptance. Only
[Windows-unit3.11 job133687146389](https://github.com/Shkirmantsev/ProjectExpert/actions/runs/43978086547/job/133687146389)
failed: one of four simultaneous cold dependency acquisitions received errno13
on `.acquire.lock`. This is a separate artifact-acquisition component, not a
repeat of the CRLF or ZIP-name failures.

The old lease created/unlinked a marker and retried only EEXIST. Windows may
report access denied while a deleted file still has outstanding handles
([Microsoft CreateFile contract](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)).
The observed failure matches that create/delete race; the CI error does not expose
an underlying Win32 code proving which handle delayed removal. The repair removes
the risky file-lifetime protocol entirely by reusing the existing bounded
kernel-owned `ProjectLock` on the same per-artifact path. No blanket permission
retry or enlarged acquisition timeout is added.

The lock file stays present; crash release belongs to the OS, and old timestamps
cannot evict an active owner. Different artifacts still acquire independent locks.
There is no new artifact/API/cache manifest format or change to source-policy,
HTTP approval, integrity checks, CPU/GPU selection or indexing parallelism.

Regression proof: stable-file and live-owner tests fail against the old marker
implementation. New coverage verifies process-death release, bounded contention,
independent artifact concurrency and real permission-error propagation. The cold
concurrency test now starts four workers through a barrier and asserts exactly one
download/publication. The artifact suite plus existing ProjectLock tests pass45
checks.100 repeated cold-concurrency tests completed400 worker requests in14.578s
on Linux, with no failures. This is concurrency software evidence, not Windows
hardware certification or a claimed GPU speedup.

Final follow-up proof: required `python3 harness.py check` **PASS:2,123 tests in163
suites,20 skips**, OpenSpec97, Wiki138 and manifest1,627. The same artifact and
ProjectLock suite also passed45 tests under Python3.11 in a cached container with
networking denied and current source mounted read-only, including the child-process
crash test. Final diff and manifest checks PASS. Fresh Windows execution after
this lock repair remains owner-push dependent; previous successful Windows peers
are evidence for the earlier candidate, not a fabricated post-repair result.

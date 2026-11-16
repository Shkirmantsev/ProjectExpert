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

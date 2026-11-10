# Verification and release acceptance

Implementation checkout: `feature/generate-init-project`, baseline `32c0c1b`.
This differs from the supplied document's inspected dev baseline. No branch switch, publication or installed-project migration was performed.
The user subsequently requested structured local commits.

## Executed evidence

- PASS: native Go tests (30k scan, hash-cache verification, exclusions before
  hashing, unsafe paths/links, backup policy and CRLF configuration), Linux build
  and Windows amd64 cross-build. Release helper uses pinned/hash-checked Go 1.27.4;
  local compatibility builds also used the available Go 1.22.2.
- PASS: real deployment-kit container build; both bundled binary checksums and
  Go build metadata verified. Standard-library runtime and compiler licence are
  shipped; code signing is not configured.
- PASS: five actual `docker compose config` profiles (base/torch, CPU, CUDA,
  Vulkan, Windows-native) retain inference services, model mounts, endpoints and
  devices. Storage overlay changes only production mounts. Base Compose forwards
  workspace mode solely so missing managed metadata fails closed.
- PASS: Linux application container readiness, MCP discovery, immediate MCP Wiki
  host write-through, project UID ownership, source read-only enforcement and
  readiness after container restart. Diagnostic hashing/minimal was used; this
  is not a semantic inference or GPU benchmark.
- PASS: failure-injected importer replay, corrupted/hash/path/collision rejection,
  shared full-build publication lease, Git/SVN identity, canonical changes,
  coordinated SQLite/WAL/FTS snapshot, secret omission, corruption/space failure,
  host verification and inactive-volume restore preserving the old runtime.
- PASS: focused Wiki/canonical/approval regressions; original Wiki flush tests
  failed before the durability fix. Canonical shard/manifest replacement now
  preserves prior bytes on failed flush and syncs ancestor entries to the mount.
- PASS: final `python3 harness.py check`: 1,803 tests across 135 suites,
  15 skips, no failed suites; Wiki/OpenSpec/configuration and the 1,488-file
  artifact manifest passed. Skips are reported rather than treated as platform
  acceptance. Final independent review found no unresolved blockers.


## Actual storage measurement

Synthetic 30,000 Markdown files, 1,657,802 source bytes, same native Linux machine,
fixed application image within the bind/volume comparison, three read/hash
measurements per mode. No GPU, model, parser or inference difference is hidden
inside these timings. Concurrent repository checks were running; this is a local
engineering measurement, not a controlled production performance acceptance.

| Operation | Measured result |
| --- | ---: |
| Initial native scan + transport + verified import | 18.1084 s |
| Unchanged full reconciliation | 5.0112 s; 0 source payload bytes |
| One same-size source edit | 4.9111 s; 48 source payload bytes |
| Bind enumerate/read/hash median | 0.9788 s |
| Volume enumerate/read/hash median | 0.9854 s |

The initial per-file fsync implementation cost 648.8534 s on this corpus. Two
Linux filesystem batch barriers reduced that cost while retaining a descriptor
opened before writes to observe asynchronous writeback errors. Journal and
publication ordering, failure propagation and recovery were separately tested.
No Linux volume-read advantage was observed; auto therefore remains bind.

The complete synthetic run also verified a skipped sparse 2 GiB dump, skipped
image archive and credential file, 20 renames/deletions, multiple SQLite databases,
FTS recovery, completed host backup verification and restore into a new runtime
volume. Raw reproducible local reports live under `tmp/local/` and are not
normative requirements or committed release artifacts.

Reproduce with matching built application/helper:

```bash
python3 scripts/test_fast_workspace_container.py --files 30000
python3 scripts/test_fast_workspace_serving.py
```

## Unverified release gates

| Platform / condition | Result |
| --- | --- |
| Linux Docker synthetic volume/import/canonical/backup/restore | PASS |
| Linux default bind compatibility and rendered accelerator profiles | PASS |
| Windows Docker Desktop native helper/PowerShell/storage/performance | NOT TESTED |
| Windows Rancher Desktop/Moby and native accelerator routing | NOT TESTED |
| Real CUDA/Vulkan/native Windows GPU execution or throughput | NOT TESTED |
| NFS/SMB source, corporate EDR and real SVN working-copy runtime | NOT TESTED |
| Host reboot/login registration and physical power-loss durability | NOT TESTED |
| Full 30k semantic/PDF ingestion, accelerator parity and stage timings | NOT TESTED |

Cross-builds, unit failures and process restart tests do not establish these
hardware/host properties. Auto promotion and complete cross-platform release
acceptance remain open; direct bind remains the compatibility default. Optional
per-user login registration is explicit; otherwise supervision is session-only.

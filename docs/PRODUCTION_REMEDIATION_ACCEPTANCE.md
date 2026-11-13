# Production remediation acceptance — 2026-11-13

Follow-up: merge-time publication is now automatic; the manual hash-entry and
second-PR instructions from the initial remediation are superseded by the
[automatic release flow](../distribution/assets/README.md#automatic-release-after-merge).
Local follow-up validation passed: full harness 1980 tests / 16 skips, actual
network-disabled asset verifier and real fixture kit build/export/negative gates.
Actual authenticated remote execution is still unverified locally.

Release status: **NOT PRODUCTION-READY**. Source corrections do not promote the
blocked asset release or certify an independent enterprise installation.

## Baseline and implementation

HTTPS fetch of `dev` returned `7099677ffd049cbcfccafff68dabe81b195bd148`.
Its tree exactly matches starting local `1d69ead`; no newer changes were overwritten.
The configured SSH remote could not authenticate, so retrieval used public HTTPS.

| Requirement | Code file / PR | Test command | Observed result | Supported platform | Remaining risk |
| --- | --- | --- | --- | --- | --- |
| Offline real GGUF CI | `.github/workflows/verify-production-runtime.yml` | Direct seeded-cache `scripts/smoke_gguf_container.py --cache <isolated-cache>` | PASS: seed twice with network none, checksums, 1507-token document and pixel-sensitive images. Root-only source assets required root seeding followed by ownership repair of only this runner cache. | Actual Linux amd64 CPU | Remote workflow rerun pending; published mode still requires real registry identity. |
| Full gates before production publication | `verify.yml`, `publish-oci-container.yml`, `verify-production-runtime.yml` | `python3 -m unittest tests.test_remediation_contract -q` | PASS: production app/kit and real-runtime publication depend on reusable full Linux/Windows verification; explicit candidate mode cannot publish. | Source workflow contracts | Remote matrix has not run on this patch. |
| Windows Compose stall diagnosis | `tests/test_workspace_deployment.py` | `python3 -m unittest tests.test_workspace_deployment tests.test_remediation_contract -q` | PASS: real profile matrix, dependency edges, timeout diagnostics. 120s render; 10s bounded Docker/Compose/context probes; stderr/duration; no speculative retries. | Actual Linux Compose; Windows-compatible Python | Physical Windows 3.13 rerun pending; original stall not reproduced here. |
| Optimized fresh defaults and status | `deployment.env`, `compose.yaml`, coordinator, semantic service, llama adapter, UI composition | `python3 -m unittest tests.test_resumable_repository_indexing tests.test_embedding_batching -q`; real offline smoke below | PASS: fresh `resumable/1/1`, explicit rollback, durable recovery/parity; effective engine visible in status. PDF workers remain one. | Actual Linux; shared Windows/Linux templates | Original large-corpus performance and Windows physical acceptance pending. |
| Preserve existing environments | `distribution/deployment/export.py` | `python3 -m unittest tests.test_remediation_contract -q` | PASS: preserved upgrade, selective preview, exact backup, atomic replacement, idempotency and blocked/tampered asset refusal. No volume/index deletion. | Actual POSIX tests; portable exporter | Migration does not make an unpublished release usable. |
| Host/engine trust distinction | `registry-preflight.sh`, `registry-preflight.ps1`, launchers | `python3 -m unittest tests.test_enterprise_ca_handshake tests.test_remediation_contract -q` | PASS: Linux preflight fixtures, valid-root success, unknown-root/wrong-host rejection. Cached assets skip HTTPS. No CA/daemon changes. | Actual Linux TLS/Bash; PowerShell source only | Host HTTPS cannot certify daemon trust; real Zscaler/Desktop/Rancher unverified. |
| Actual OCI assets and matching kit | `publish-offline-assets.yml`, generated CI/kit release record | Anonymous `docker buildx imagetools inspect <documented-candidate-tag>` | Initial anonymous GHCR inspection returned 403; no published digest was observed locally. Trusted merge jobs now resolve/build/publish and pass the real digest automatically. | No published release certified | Observe authenticated automatic merge run and independently install its emitted matching kit. |
| Other APIs and heterogeneous work | Investigation and measured experiment below | `python3 tmp/local/remediation/run_device_benchmark.py` (local experiment) | CPU/iGPU parity PASS; slower joint work correctly rejected. | Actual Ryzen CPU / AMD Vulkan iGPU | Automatic full-pipeline combination selection, other hardware and reviewed alternative adapters incomplete. |

## Model and local hardware identities

- Approved asset manifest SHA-256: `f3bd07b7dc304c73d5166a447fd50280fdf5e69cb9de9f7075f3c354b0db2f25`.
- Actual approved local asset image ID: `sha256:b30470440edc1dc84abf6e78d8c97fb1376950746ddc4b42cce3800162e257da`; RepoDigests is empty. This is not a registry identity.
- Runtime actually pulled from GHCR: `ghcr.io/ggml-org/llama.cpp:server-vulkan-b11515@sha256:b7ac2b757dd43ab04fdc236b9e96a0020ba8566d0b8c33839add482e93c80f3b`.
- CPU: AMD Ryzen 7 5700U, 8 cores / 16 logical processors. Linux x86-64, kernel 6.14.0-37-generic; Docker client/engine 29.9.3; Compose 5.7.0.
- Physical iGPU: PCI `0000:03:00.0`, vendor/device `1002:164c`; pinned runtime reports `Vulkan0: AMD Radeon Graphics (RADV RENOIR)`.
- Runtime-reported memory is shared UMA, not independent dedicated VRAM. Each model runtime used eight CPU threads. Discrete GPU and physical Windows hosts were unavailable. Container Mesa Vulkan driver package: `26.0.8-1ubuntu0.3`.

## Measured fixture results

Generated Markdown fixture: 100 sources / 800 chunks; Python 3.12.3; hashing
embeddings, identical canonical generation/chunk identities. Command:
`python3 scripts/benchmark_indexing.py --files 100 --sections 8 --repeats 2 --output tmp/local/indexing-benchmark/remediation.json`.

| Mode | Cold seconds | Warm seconds |
| --- | ---: | ---: |
| Legacy serial | 0.949 | 0.268 |
| Resumable serial | 1.678 | 0.517 |
| Resumable parallel | 2.103 | 0.651 |

This small fixture shows overhead, **not** an indexing speedup. It does not
satisfy original-corpus, real PDF, 80k+ chunk, RSS/VRAM/IO or p50/p95 acceptance.

Actual pinned Gemma comparison used 16 generated technical documents, batch size
8, three repeated rounds, three queries and the existing
`benchmark_document_endpoints`/`MultiEndpointEmbeddingModel` gate. Both endpoints
ran on an internal Docker network after network-disabled seeding; the client
used the existing locked dependency image with current source mounted. No HF
model acquisition occurred. Raw reproducible local experiment scripts/results
remain under `tmp/local/remediation/` and are not release artifacts.

| Execution | Completed documents/sec, three rounds |
| --- | --- |
| CPU | 4.600 / 5.011 / 5.257 |
| AMD Vulkan iGPU | 9.966 / 10.301 / 11.390 |
| CPU + iGPU | 9.035 / 9.924 / 9.903 |

Numerical parity passed: minimum cosine 0.999874, maximum absolute difference
0.002634. Individual and combined top-3 rankings matched all three queries.
Other verification/build work was active, and no isolated thermal/RSS telemetry
was captured; these exploratory rates do not certify a release configuration.
Joint admission correctly refused the combination: its samples did not exceed
the fastest standalone samples. These are adapter document-fixture rates,
including live identity checks, **not end-to-end repository indexing or nDCG
certification**. The dependency image was local
`sha256:d01f1db186328b47862fcebad2d15a581c7725daa9f57dcda79776098fc9d14b`.

## Alternative backend investigation

The pinned [llama.cpp b11515 build guide](https://github.com/ggml-org/llama.cpp/blob/b11515/docs/build.md)
documents SYCL for Intel GPU/iGPU, HIP for supported AMD GPUs with ROCm, and
OpenCL for recent Adreno. DirectML is absent from its documented backend list.
This does not establish parity for this model. The reviewed kit packages CPU,
CUDA-container and Vulkan runtimes; no reviewed SYCL/HIP/OpenCL/DirectML runtime
or model-operation acceptance is present. This host has no Intel/Adreno GPU or
Windows DirectML environment. A HIP package for this AMD device still requires
runtime/driver compatibility, redistribution review and real model parity proof;
it cannot be inferred from the display driver. These are open implementation
gates, not evidence that other APIs can never work. CPU/Vulkan fallback remains.

Registry trust paths were checked against the [official Docker certificate guide](https://docs.docker.com/engine/security/certificates/).
Container CA merging cannot repair Docker daemon trust. A local TLS fixture
checks valid-root success, unknown-root rejection and wrong-host rejection;
it is not a physical Zscaler test.

## Real offline changed-source acceptance

`python3 scripts/smoke_production_container.py --image projectexpert:remediation-source-validation --candidate-assets --asset-image sha256:b30470440edc1dc84abf6e78d8c97fb1376950746ddc4b42cce3800162e257da --manifest-sha256 f3bd07b7dc304c73d5166a447fd50280fdf5e69cb9de9f7075f3c354b0db2f25`

**PASS**: fresh named model cache, network-disabled seeding/setup, internal-only
runtime network; actual scanned OCR, table/figure mapping, complete local tokenizer,
wide text/query, pixel-sensitive images, native Torch, optimized indexing,
readiness, UI/MCP, dependencies, repository-owner writes and restart.
The smoke asserts the reported effective indexing engine is `resumable`.
Only its own temporary resources were removed afterward.

Validation image ID: `sha256:1b23a4f0b5b0433e70ccc420e72dc0068a17bc334fd30ede54bc987f82025045`.
It reuses the prior verified local production dependency image and overlays current
source into both source and installed package locations; `pip check` passed.
It is a local candidate, not an independently installed released kit. The canonical `Containerfile --target production` build also passed the exact
dependency, parser/import and redistribution/license gates. Its finalized image is
`sha256:72493341f0934201e297aa3c591d86c9d59cb1c8b8e9ddb41eb5a3b2ae7d249a`
with empty RepoDigests. `docker run --rm --network none --entrypoint python
projectexpert:remediation-candidate -m pip check` passed.

The same full fresh-volume smoke was repeated with
`--image projectexpert:remediation-candidate`: **PASS**, including actual OCR,
all model consumers, optimized engine status, UI/MCP and restart. Both source
validation and canonical acceptance completed and removed only their own
temporary resources. This remains a local candidate, not registry or independent
enterprise release acceptance.

## Verification and outstanding release gates

**PASS:** `python3 harness.py check` completed with 1,970 tests and 16 skips,
including final artifact verification. The active OpenSpec change verification
record retains earlier failures and their corrections. Earlier complete runs
reached the final manifest gate while documentation was changing; hashes were
regenerated and independently verified. No test was disabled for that failure. Remote workflows have not been rerun by this local patch. No new
published app/asset/kit RepoDigest, license approval or Windows acceptance is claimed.
The existing reviewed inventory/notices were retained unchanged. Fresh release
signature, CodeQL and registry SBOM acceptance were not executed by this local run.

Outstanding: authenticated asset publication/pin, matched released kit,
independent no-HF installation, physical Windows Desktop/Rancher, actual corporate
CA/engine pulls, original large corpus performance/recovery, adaptive resource
measurements and automatic validated heterogeneous selection on supported hosts.

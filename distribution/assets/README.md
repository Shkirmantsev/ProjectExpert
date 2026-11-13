# Immutable offline asset release

Trusted merges automatically resolve or publish reviewed model assets and embed
their actual immutable registry identity in the tested deployment kit. No manual
checksum input or second metadata PR is required. `assets-lock.json` contains the
operator-reviewed per-file inventory/notices. The Git `asset-release.json` is an
unbound source template; CI generates the concrete release record. Clients still
refuse missing/corrupt packs and never fall back to Hugging Face. Successful remote
publication must be observed; this local source change does not claim it happened.

## Controlled assembly and review

Use an empty controlled build directory with at least 8 GiB free. Network access
is allowed only here, before OCI distribution, not on installation clients:

```bash
python scripts/materialize_asset_pack.py --output tmp/local/asset-pack
```

The assembler fetches immutable upstream revisions, verifies known GGUF/archive
hashes, computes each materialized file's SHA-256 and records provenance. It
includes the full pinned Transformers model/tokenizer (including model and
processor configs), the custom Docling layout/accurate TableFormer/OCR tree,
native Windows Vulkan archives and extracted files by default. Container CUDA
uses the separately pinned llama.cpp runtime image and the host NVIDIA driver;
it does not require installing a CUDA toolkit on the host. Windows native CUDA
redistributables require an explicit `--native-backends cuda vulkan` selection
and their own redistribution review. No pack installs or replaces host drivers.
Its candidate manifest
is always `blocked`, with no invented license approval. A partially failed
assembly cannot be seeded. Never modify an installed pack in place.

An explicit repeatable `--download-cache PATH` reuses a file only after matching
its expected upstream checksum; it does not trust cache names alone. The
`candidate` Containerfile target checks provenance and integrity of a blocked
inventory, but its normal entrypoint still refuses activation. The default
`verified` target retains the full redistribution and activation gates.

`smoke_production_container.py --candidate-assets` supports local acceptance
with an actual Docker image ID and independent manifest hash. This is separate
from registry publication and does not promote the canonical release metadata.
The smoke uses container-local HTTP on an internal network, so it needs no
host access to an isolated bridge's published ports.

PR CI invokes `scripts/prepare_ci_assets.py --candidate`: it computes SHA-256
from the committed reviewed inventory, checks dependency compatibility and retained
notices, materializes that exact pack on the controlled build runner, and returns
an actual local Docker image ID for offline acceptance. It removes only its own
raw pack after image verification; existing build directories are never overwritten.
PR jobs cannot publish or activate a production kit.

Trusted merge pipelines call the reusable `publish-offline-assets` workflow
automatically. See the automatic release flow below. The source
`asset-release.json` remains an unbound template; its `blocked` status does not
require a second metadata PR. The normal `deployment-kit` target accepts the
CI-verified immutable asset image and computed manifest hash as build arguments,
validates them against the reviewed inventory, and embeds the matching actual
asset/app identities. Without either those verified inputs or an existing
verified release record it still fails closed. Candidate kits remain unpromoted.

The approved redistribution review checks no-fee commercial use at any
company size. The pack uses Apache-2.0, MIT, CDLA-Permissive-2.0 and the
retained LLVM/OpenMP/Intel notices. These grants do not impose revenue or company
size limits; their copyright, license and applicable notice obligations remain.
The TableFormer declaration includes both CDLA and Apache terms. The bundled
OpenMP DLL must retain its complete supplied notice rather than being classified
as blanket MIT. Primary terms: [Apache](https://www.apache.org/licenses/LICENSE-2.0.txt),
[MIT](https://opensource.org/license/mit),
[CDLA](https://cdla.dev/permissive-2-0/) and the exact upstream
[Vulkan archive with OpenMP notice](https://github.com/ggml-org/llama.cpp/releases/download/b11515/llama-b11515-bin-win-vulkan-x64.zip)
retained in the Vulkan archive. The operator approval and technical evidence are
recorded in [the retained review](licenses/asset-review.json). Approval of the
inventory does not claim registry publication or physical-platform certification.

Review every file's redistribution terms, including model weights, native DLLs
and notices. A reviewed manifest must supply `license` and `license_evidence`
for every file; evidence must itself be hashed/inventoried. Preserve exact source,
revision and SHA-256, and the exact `production_lock_sha256`. The compatibility
contract is `llama-b11515/docling-production-lock`. Optional independent evidence
files can be supplied under `--license-evidence`; they must all be in the review.
Reassemble into a fresh directory with the independently pinned review:

```bash
python scripts/materialize_asset_pack.py --output tmp/local/asset-pack \
  --reviewed-manifest /reviewed/manifest.json \
  --reviewed-manifest-sha256 "$PI_ASSET_MANIFEST_SHA256" \
  --license-evidence /reviewed/licenses
python -m pi_platform.deployment.offline_assets --root tmp/local/asset-pack \
  --manifest-sha256 "$PI_ASSET_MANIFEST_SHA256"
docker build -f distribution/assets/Containerfile \
  --build-arg PI_ASSET_MANIFEST_SHA256="$PI_ASSET_MANIFEST_SHA256" \
  -t ghcr.io/shkirmantsev/project-intelligence-assets:reviewed-candidate .
```

## Automatic release after merge

Merge the reviewed changes into `dev` or `development` (also supported: `main`).
No manual workflow run, copied checksum or second metadata PR is needed.

1. `publish-oci-container` invokes reusable `publish-offline-assets`. Its
   `GITHUB_TOKEN` authenticates to GHCR with package-write permission.
2. The resolver computes SHA-256 from the exact bytes of committed
   `distribution/assets/assets-lock.json`. This is a checksum, not an SSH key
   or a value an operator must obtain from an AI. The inventory must already
   carry per-file hashes, license evidence, review status and compatible locks.
   Computing its checksum never approves new licenses automatically.
3. It checks `ghcr.io/shkirmantsev/project-intelligence-assets:manifest-<computed-sha>`.
   A matching pack is verified with the current source verifier and reused
   without upstream model downloads. Explicit absence or a mismatched payload
   triggers controlled pinned materialization, verified image build and push.
   Authentication, TLS, daemon and network errors fail clearly; they are not
   interpreted as missing models. Publishers are serialized across workflows.
4. The actual observed registry RepoDigest becomes a job output. The consuming
   job pulls/verifies that immutable image and generates
   `tmp/local/ci-assets/{asset-release,assets-lock}.json`. These generated records
   are retained as a workflow artifact; the Git source template is not rewritten.
5. Full Linux/Windows tests and real egress-denied OCR/tokenizer/GGUF/indexing/
   restart acceptance gate application and deployment-kit promotion. The kit
   embeds this same asset digest and the actual published application digest.

`verify-production-runtime` consumes the same reusable resolver. PRs and explicit
manual candidate tests remain unpromoted and never publish model images.
The standalone `publish-offline-assets` UI button remains available for diagnostics
without a required hash input; ordinary merges invoke it automatically.

For a personal/development PC, after authenticating Docker to GHCR with package
write permission, the same resolver is available explicitly:

```bash
python3 scripts/prepare_ci_assets.py --ensure-published --env-output tmp/local/asset-env
```

Only the personal PC/controlled builder may execute this upstream-build command.
Enterprise installation continues to pull prebuilt immutable OCI images and
seed locally with networking disabled; it never materializes models from HF.
A denied GHCR token/package policy still requires repository/package access to
be corrected; the pipeline cannot manufacture registry permissions. No published
identity or successful remote run is claimed until actually observed.

## Consumers and promotion

Normal Compose always runs asset-seed with networking disabled before both
model-setup and production. Model setup is also network-disabled and provisions
verified GGUF copies plus the private runtime key/controller interpreter.
Consumers resolve the pinned `/models/asset-packs/<manifest-sha256>/` directory:
`embedding/`, `transformers/gemma/`, `docling/artifacts/`, `docling/ocr/`, and
`windows/{cuda,vulkan}/`. The mutable active pointer is informational only.
Native Windows uses `docker create`/`docker cp`, verifies the complete local pack
in a network-disabled application container, and only then probes its native
executables. No host HF/GitHub model/runtime downloader remains.

The production workflow requires the reviewed inventory/digests, seeds an empty
volume twice without networking, then runs the exact application image on an
internal Compose network. Real OCR, table/figure detection, tokenizer, wide-text,
query/image embeddings, indexing and restart must pass. `verify-asset-pack` also
runs automatically for relevant changes; it is no longer a manual-only gate.
The deployment-kit build bakes the automatically resolved immutable pins into fresh deployment.env. Existing
`--upgrade` preserves operator deployment.env, reports stale/missing pins and
backs up managed files. No user volume is deleted.

Physical Windows GPU, Rancher/Desktop and published-registry acceptance remain
release evidence to collect. Complete local offline acceptance is recorded below;
unit fixtures are never physical-platform or publication evidence.

## Local acceptance evidence — 2026-11-12

The complete production smoke passed with a fresh model volume and an internal
Docker network: real OCR, tables/figures, local tokenizer, wide text/query,
pixel-sensitive image vectors, native Torch, indexing, UI, MCP, dependency check,
repository-owner writes and restart. It found and reproduced two integration
defects, now fixed: root-only staging permissions and installed-wheel lock lookup.
The final canonical production-target build passed its parser and license gates.

Local image IDs (these are **not published OCI RepoDigests**):

- `projectexpert:offline-candidate`: `sha256:d01f1db186328b47862fcebad2d15a581c7725daa9f57dcda79776098fc9d14b`
- `projectexpert-assets:reviewed-local`: `sha256:3a0237d157201d3da14dbbdbc0296c561ed0dae260556530b7b073e8decc84ba`
- Local test manifest: `47c82e536d1c20460beff86d7d37f1652fe592acb7caabb02bf8469286f2410d`

The inventory contains 82 artifact files (2,919,769,070 bytes) plus seven retained
notice/review files. The operator subsequently approved the classifications and
notices; the canonical 89-file manifest is
`f3bd07b7dc304c73d5166a447fd50280fdf5e69cb9de9f7075f3c354b0db2f25`.
All original artifact hashes and provenance are unchanged. This supersedes the
earlier local-only review above; its historical image IDs remain local test evidence.

The final approved image `projectexpert-assets:approved` is
`sha256:b30470440edc1dc84abf6e78d8c97fb1376950746ddc4b42cce3800162e257da`.
Complete fresh-volume production acceptance and restart passed again against
this exact approved manifest/image, with external egress denied. Superseded
local-only candidate images and unused build cache were removed; current images
and existing user services/volumes were retained. This image ID still is not a
published registry RepoDigest.

A separate real AMD integrated-GPU Vulkan smoke passed inside an internal network
with the runtime-reported `Vulkan0` device, a 1,507-token document and distinct
red/blue image vectors. Vendor-neutral unit fixtures cover Intel, AMD, NVIDIA
and an unknown vendor. Physical Windows CUDA/Vulkan, Rancher/Desktop and the
published-release identity remain unverified. PowerShell 7 launcher/extraction/
container-CUDA contracts passed locally; Windows 5.1 execution remains a CI gate.
The source harness passed 1,955 tests with 16 skips.

Implementation references: GitHub documents [reusable workflow outputs and inherited secrets](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)
and [repository/package linking for workflow access](https://docs.github.com/en/packages/learn-github-packages/connecting-a-repository-to-a-package).
The asset image carries the repository source label; the workflow retains explicit
package-write permission and does not bypass repository/package access policy.

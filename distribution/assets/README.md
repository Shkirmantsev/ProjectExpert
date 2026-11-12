# Immutable offline asset release

The release is **BLOCKED**. `assets-lock.json` records the materialized file inventory
but its redistribution classifications remain unapproved, and
`asset-release.json` has no published digest. The standard deployment now refuses
missing packs/pins; it never silently falls back to Hugging Face. This source
change alone does not make a fresh installation usable. The actual reviewed OCI
pack must be published before production/kit promotion can pass.

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
redistributables require an explicit `--native-backends cuda,vulkan` selection
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

The local technical redistribution review checks no-fee commercial use at any
company size. The proposed pack uses Apache-2.0, MIT, CDLA-Permissive-2.0 and the
retained LLVM/OpenMP/Intel notices. These grants do not impose revenue or company
size limits; their copyright, license and applicable notice obligations remain.
The TableFormer declaration includes both CDLA and Apache terms. The bundled
OpenMP DLL must retain its complete supplied notice rather than being classified
as blanket MIT. Primary terms: [Apache](https://www.apache.org/licenses/LICENSE-2.0.txt),
[MIT](https://opensource.org/license/mit),
[CDLA](https://cdla.dev/permissive-2-0/) and the exact upstream
[Vulkan archive with OpenMP notice](https://github.com/ggml-org/llama.cpp/releases/download/b11515/llama-b11515-bin-win-vulkan-x64.zip)
retained in the Vulkan archive. This technical review of a local test pack does
not constitute operator approval or canonical release promotion.

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

The OCI build never fetches models. The `publish-offline-assets` workflow can perform the same controlled assembly,
build and idempotent offline seeding from the committed independently pinned
review; it publishes a **candidate** and records the real RepoDigest. It cannot
run with the current blocked inventory and never self-approves licenses.

Publish the reviewed image through authorized
registry credentials and capture its real RepoDigest. Commit the exact reviewed
manifest bytes as `assets-lock.json`. Set `asset-release.json` to `verified`,
with `image: ghcr.io/shkirmantsev/project-intelligence-assets@sha256:<actual digest>`
and the independent manifest SHA-256. No placeholder digest is acceptable.

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
The deployment-kit build bakes reviewed pins into fresh deployment.env. Existing
`--upgrade` preserves operator deployment.env, reports stale/missing pins and
backs up managed files. No user volume is deleted.

Physical Windows GPU, Rancher/Desktop, registry trust and full offline acceptance
are still release evidence to collect. Unit fixtures are never that evidence.

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

The factual canonical inventory contains 82 files (2,919,769,070 bytes); the local
test pack adds seven inventoried notice/review files. Canonical classifications
remain unset following automatic approval review; local technical review and
these measurements do not grant public redistribution approval.

A separate real AMD integrated-GPU Vulkan smoke passed inside an internal network
with the runtime-reported `Vulkan0` device, a 1,507-token document and distinct
red/blue image vectors. Vendor-neutral unit fixtures cover Intel, AMD, NVIDIA
and an unknown vendor. Physical Windows CUDA/Vulkan, Rancher/Desktop and the
published-release identity remain unverified. PowerShell 7 launcher/extraction/
container-CUDA contracts passed locally; Windows 5.1 execution remains a CI gate.
The source harness passed 1,955 tests with 16 skips.

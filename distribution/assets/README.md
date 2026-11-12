# Immutable offline asset release

The release is **BLOCKED**. `assets-lock.json` is not a completed inventory and
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
native Windows CUDA/Vulkan archives and extracted files. Its candidate manifest
is always `blocked`, with no invented license approval. A partially failed
assembly cannot be seeded. Never modify an installed pack in place.

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

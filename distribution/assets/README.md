# Immutable asset pack

Release status is **blocked**, as recorded in `assets-lock.json`. No file hash,
model redistribution decision, benchmark result or OCI digest is invented.
Existing reviewed GGUF/projector hashes remain in deployment/accelerator-lock.json.

A release engineer must assemble `tmp/local/asset-pack/manifest.json` and all
materialized files. Every file entry requires `path`, `sha256`, `source`,
immutable upstream `revision`, `license` and `license_evidence`. License evidence
must itself be inventoried and hashed. Set `schema_version: 1`,
`runtime_compatibility` and `release_status: verified` only after actual review.
Uninventoried files and symlinks are rejected. Required families include the
GGUF/projector, complete tokenizer, Docling layout/TableFormer/OCR configs and
weights, native Windows executables/DLLs and notices.

Validate locally using the independently reviewed manifest digest:

```bash
python -m pi_platform.deployment.asset_pack --source tmp/local/asset-pack \
  --manifest-sha256 "$PI_ASSET_MANIFEST_SHA256" --verify-only
docker build -f distribution/assets/Containerfile \
  --build-arg PI_ASSET_MANIFEST_SHA256="$PI_ASSET_MANIFEST_SHA256" \
  -t project-intelligence-assets:candidate .
```

The dedicated Containerfile.dockerignore includes only the verifier and the
assembled local pack. Build never downloads assets. Published pack entrypoints
perform seed verification again; the application/seeder manifest pin must come
from the reviewed deployment configuration, not from inside the untrusted pack.
The manual `verify-asset-pack` workflow exercises idempotent seeding with
networking denied; this is **not** a substitute for actual Docling/embedding/
Windows runtime smoke tests with empty HF cache and denied network.

Production adoption additionally requires pinning the actual published OCI
digest, end-to-end model-setup and native extraction integration, and changing
loaders to digest-addressed paths. Until those gates pass, the default kit
continues its existing downloads. An offline-capable parser path can be tested
with `PI_DOCLING_ASSET_ROOT` pointing to the pack's `docling` directory and
`PI_DOCLING_TOKENIZER` pointing to the materialized tokenizer directory.

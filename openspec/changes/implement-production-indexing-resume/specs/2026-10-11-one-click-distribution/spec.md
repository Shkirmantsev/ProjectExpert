## ADDED Requirements

### Requirement: Mandatory verified offline model distribution
The standard deployment MUST seed an independently pinned, reviewed immutable OCI
asset image before model setup and production startup for every supported backend.
The pack MUST contain complete pinned embedding/projector, tokenizer, Docling
layout/table/OCR and native Windows runtime files with per-file hashes and
redistribution evidence. Production MUST use verified local assets and MUST NOT
fall back to HF/GitHub model downloads. Missing release pins or corrupt/missing
assets MUST fail before indexing writes, without deleting existing data.

#### Scenario: Fresh offline deployment
- **WHEN** the standard deployment starts with empty model-cache after registry pulls
- **THEN** seeding runs without networking and setup, real OCR/table/figure conversion, tokenizer and text/image inference succeed without public egress

#### Scenario: Release pack is unavailable
- **WHEN** reviewed inventory, release digest or required files are unavailable
- **THEN** promotion/startup fail with an actionable missing-offline-asset diagnosis and preserve existing index/cache data

#### Scenario: Existing kit is upgraded
- **WHEN** an operator uses the backed-up kit upgrade path
- **THEN** managed templates update, deployment.env remains preserved, and missing/mismatched asset pins are explicitly diagnosed

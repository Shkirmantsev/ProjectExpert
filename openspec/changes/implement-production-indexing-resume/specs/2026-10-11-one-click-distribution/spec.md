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

#### Scenario: Managed GPU runtime reuses host drivers
- **WHEN** the container engine exposes a compatible GPU and host driver
- **THEN** the launcher probes the pinned application runtime and selects an actual reported device without installing or replacing host drivers or toolkits
- **AND** unavailable or failed GPU startup follows the validated CPU fallback

#### Scenario: Native runtime inventory is explicit
- **WHEN** the default Windows asset pack is assembled
- **THEN** it declares its included Vulkan backend and does not require NVIDIA native CUDA redistributables for container CUDA
- **AND** requesting an omitted native backend fails with an actionable diagnosis

#### Scenario: Seeder and application use different identities
- **WHEN** a root seeder publishes verified public model assets with a restrictive umask
- **THEN** the non-root application can traverse pack directories and read every inventoried asset without modifying their hashes

#### Scenario: A reviewed PR precedes registry publication
- **WHEN** source or PR verification runs before the asset image is published
- **THEN** it builds the approved independently pinned inventory as a local image and exercises offline seeding and actual production acceptance without changing canonical publication metadata
- **AND** source workspace/export checks use the candidate kit while production publication and normal release-kit builds still require the actual immutable registry digest

#### Scenario: selective operator environment migration
- **WHEN** an operator previews migration of indexing defaults or verified asset pins
- **THEN** no files are changed
- **WHEN** the operator explicitly applies the selected migration
- **THEN** only the selected keys change atomically with an exact environment backup
- **AND** blocked or mismatched asset metadata is refused before environment mutation

#### Scenario: registry trust diagnosis before launcher pulls
- **WHEN** startup needs an uncached asset image
- **THEN** a read-only preflight reports Docker context and separate host/engine trust guidance
- **AND** no CA store, system driver or daemon setting is changed
- **AND** cached-image startup does not depend on remote registry preflight success

### Requirement: Automatic merge-time offline asset publication
Trusted merges into dev/development MUST automatically resolve the reviewed model
asset image before application and deployment-kit publication. The pipeline MUST
compute SHA-256 from the committed reviewed inventory without operator hash entry.
It MUST reuse a matching registry image or build/publish missing or mismatched
assets only on the controlled release runner, then pass the actual immutable
registry digest to offline acceptance and the matching kit in the same run.
No second source edit or PR MUST be required to record that generated identity.
Human inventory/license review, real offline acceptance and immutable pin checks
MUST remain enforced. PRs MUST NOT publish assets or promote a release.

#### Scenario: matching published pack exists
- **WHEN** a trusted merge finds a verified matching content-keyed registry image
- **THEN** it uses that image by actual registry digest without upstream downloads

#### Scenario: pack is missing or its payload does not match
- **WHEN** the registry explicitly reports the pack missing or verification detects a mismatched payload
- **THEN** controlled CI materializes the reviewed pinned files and publishes a verified replacement
- **AND** subsequent consumers use its observed immutable registry digest

#### Scenario: authentication or network failure
- **WHEN** registry access is denied or unavailable
- **THEN** CI fails with an actionable error rather than treating that condition as absent models or bypassing verification

#### Scenario: automatic matched kit
- **WHEN** full tests and actual offline application acceptance pass
- **THEN** the kit embeds the same verified asset digest and actual published application digest without a manual metadata PR

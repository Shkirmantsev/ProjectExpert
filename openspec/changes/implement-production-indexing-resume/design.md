# Design

Reference: user-supplied Production Indexing Resume Performance Design V2,
2026-11-11; implementation follows its authoritative Appendix A over conceptual
schema examples. Work is on feature/generate-init-project, not document's dev.

## Boundaries
Keep public index_repository signature and runtime.extra. Caller still validates
snapshot and publishes; coordinator returns an unpublished candidate. Source
workers use isolated buffers; one locked connection serializes atomic commits.
Canonical reads are streamed through generation membership, never _store shims.
Use OS advisory exclusion plus monotonically increasing database fences. Keep
legacy ingestion.json intact and back it up before one-time transactional import.
Metadata, pipeline key and source content hash are independent reuse dimensions.

## Artifacts
FTS builds bounded idempotent batches into a candidate database. SQLite backup,
integrity/count validation, close, fsync and same-volume replacement produce a
standalone artifact. Graph shards use deterministic atomic per-shard files and
checksums; interrupted shards are reconciled before reuse. Dense vectors retain
existing profile namespaces. Completed vector batches survive failed ANN builds.

## Concurrency and failures
Parallel work admits bounded source tasks and CPU capacity, excludes shared PDF
handles, and applies backpressure. A source failure blocks complete publication
unless explicitly allowed by the operator. DB corruption, disk errors, immutable
address conflicts and stale fences fail closed; state is never deleted to retry.

## Rollout
Fresh defaults are PI_INDEX_ENGINE=resumable, PI_INDEX_PARALLEL=1 and
PI_EMBED_BATCHING=1. Explicit legacy/serial overrides remain supported without
silent fallback. Existing environments are preserved; explicit selective migration
previews changes and atomically applies them with an exact backup. PDF concurrency
remains one until real RSS admission is validated. Production promotion still
requires packaged-model performance, recovery and physical-platform acceptance.
Offline assets are mandatory and fail closed until the real digest is published.
No test fixture or fake embedding is evidence of actual hardware throughput.

## Offline release remediation (2026-11-12)
The follow-up user audit supersedes the optional offline rollout in this proposal.
The default exported topology must seed a reviewed digest-addressed asset image
with networking disabled before model-setup and application startup. No default
HF/GitHub model or host-runtime downloads are permitted. Missing release pins
block startup and production publication, with an explicit kit-upgrade diagnosis;
existing volumes, caches, deployment.env and index data are retained. Developer
model pulls remain explicit and cannot bypass production offline configuration.
Pack paths are embedding/, transformers/gemma/, docling/artifacts/, docling/ocr/,
and windows/{cuda,vulkan}/. Full tokenizer/native/model loading and egress-denied
PDF/text/image/restart acceptance remain required release gates. Neither a test
fixture nor a materialized unreviewed candidate can populate verified release pins.

The user clarified that application runtimes must reuse existing host drivers.
Windows prefers managed container CUDA when the engine exposes it, then follows
the existing native/CPU fallback. The default native pack declares Vulkan only;
native CUDA redistributables are an explicit separately reviewed option. Linux
selection uses actual runtime device evidence across GPU/iGPU vendors. No route
installs or replaces host drivers/toolkits. Redistribution review must address
no-fee enterprise use without company-size or revenue limits and retain required
notices; technical local-test classifications do not authorize public release.

Local candidate acceptance requires an actual Docker image ID and independent
manifest hash, without altering canonical release metadata. Isolated HTTP clients
run inside the test network. Seeded public assets are readable by the application
UID after atomic publication, including when the seeder has a restrictive umask.
Installed-wheel checks resolve the lock from the image's explicit application
home and continue checking its exact hash.

PR/source validation must be possible before registry publication. Its explicit
CI candidate preparation validates the canonical approved manifest, independent
pin, lock and notices before materialization, then supplies an actual local
image ID to denied-egress acceptance. It does not rewrite release metadata.
Workspace/export checks use `deployment-kit-candidate`; published kit builds
continue through the separate strict `deployment-kit` release gate. Non-PR
production promotion still requires the actual immutable registry identity.

## Automatic merge-time publication follow-up
Trusted dev/development/main runs call the reusable asset publisher. It computes
the reviewed manifest hash; uses a content-keyed registry tag only as a lookup
hint; and verifies the immutable RepoDigest against current source/lock policy
with network none. Explicit absence or payload mismatch rebuilds once on CI;
authentication/TLS/network/daemon failures do not trigger upstream assembly.
Publishers serialize across callers. Unreviewed inventories fail before network work.
The resulting immutable image is passed as a job output; consumers independently
pull/verify it and generate release evidence under tmp/local/ci-assets. Smoke
reads that generated record and kit build arguments bind the same image/hash
against the reviewed manifest. Source release metadata remains unbound rather
than requiring a circular second PR. Full tests and real offline smoke precede
application/kit promotion. PR jobs build local candidates and never publish.

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
PI_INDEX_ENGINE=legacy|resumable is explicit, without silent fallback. Keep new
engine opt-in until migration/restore and packaged SQLite release proof pass.
PI_INDEX_PARALLEL and PI_EMBED_BATCHING stay individually gated. Offline asset
requirements cannot be enabled by default until a real pinned pack is published.
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

---
id: adr.0037-isolated-offline-windows-cuda-runtime
title: Isolate optional offline Windows CUDA from the primary asset pack
kind: adr
status: accepted
summary: Restore native CUDA without container GPU passthrough or changing the reviewed Vulkan/model pack.
sourceRefs:
  - pi_platform/deployment/native_runtime_assets.py
  - distribution/deployment/native-runtime-assets.ps1
  - distribution/deployment/setup-windows-accelerator.ps1
  - distribution/deployment/WINDOWS_NATIVE_GPU_RECOVERY.md
---

# Decision

Use a separately inventoried, exact-primary-manifest-bound native Windows CUDA
pack. Retain the reviewed main model/Docling/Vulkan inventory unchanged. Support
offline operator-local inspection/import now and resolving a future independently
approved immutable OCI companion through the same verifier. No public companion
or NVIDIA redistribution approval is created by this implementation.

Native CUDA is necessary on Windows engines such as the reported Rancher Desktop
without NVIDIA passthrough: it uses the existing host driver and an authenticated
host endpoint, rather than changing Docker or installing a toolkit. Intel Vulkan
remains a native alternative, explicitly probed instead of inferred from PATH.

# Boundaries

Candidates are blocked. Human approval must cover exact per-file licenses and a
scoped evidence file. A pinned manifest, exact upstream archives, extracted binary
closure, provenance, Windows path/case semantics and complete inventory are checked
before execution. Staging is private and final directories are hash-addressed;
cache reuse verifies bytes, never merely a marker. DLL search is isolated from
user/global CUDA PATH entries. The default asset license exclusions stay intact.

Short-lived probes use .NET Process with asynchronous streams and timeout cleanup;
long-lived native server identity includes PID/path/start time. Concurrent pipe
reads follow the [Microsoft process stream guidance](https://learn.microsoft.com/en-us/dotnet/api/system.diagnostics.process.standardoutput?view=netframework-4.8.1). A serving-path
embedding smoke validates actual authenticated Docker-to-host inference before
native activation. Explicit CUDA/Vulkan preserves operator intent, with CPU fallback
or strict refusal; auto retains measured speed selection. Private plan/probe evidence
records the request, selection and reasons without API keys.

Source indexing, Git export, model/profile identity and private cache formats do
not change. CPU skips optional native copy/probes. Switching a transport alone does
not invalidate warm source/vector work. Existing processes/caches are not removed
on asset rejection. Rollback selects an old kit or CPU/Vulkan, without pruning data.

# Consequences and verification limits

One-time operator-local review is more work than an approved distributable image,
but permits corporate offline use without pretending NVIDIA redistribution is
approved. Public build/publication is deferred until a real inventory/legal review;
no placeholder OCI digest can activate it. Only a physical Windows workstation
can establish MX550/Intel operation, memory fit, firewall routing and throughput.
Linux PowerShell7 process and mocked routing checks are software evidence only.

See [operator recovery](../../../distribution/deployment/WINDOWS_NATIVE_GPU_RECOVERY.md). Current
OpenSpec adoption remains separate from the active recovery change.

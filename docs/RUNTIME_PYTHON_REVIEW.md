# Runtime, Wiki and Python review — 2026-10-26

Scope: implementation changes since `8a2dcddecb85ae7043f03916fc48017397620749`.
This records local evidence; it does not certify a published image or every GPU.

## Corrected defects

- Release smoke scripts and real-model CI referenced the retired Qwen interface.
  They now use Gemma and CI starts the authenticated GGUF endpoint before tests.
  The source installation and runtime workflow install both production locks.
- A standalone production container selected GGUF without supplying a server.
  It now defaults to native `gemma-torch`; the kit retains managed GGUF inference.
- Bootstrap-generated settings caused a second refresh and transient 503 after
  readiness. The monitor now accepts the version actually published by bootstrap.
- Linux GPU enumeration could pass while actual model startup failed. Candidate
  inference and benchmark validation now participate in fallback selection.
- Windows native startup could publish a plan despite readiness timeout; device
  probe evidence and endpoint credentials were also lost in measurement. Setup
  failures now fall back to CPU, and non-start commands reuse the saved plan.
- Wiki relative roots and symlink paths were unsafe. Reads and reserved writes
  reject symlink paths; atomic writes use unique temporary files. Mutations are
  serialized within a process, and audit append errors are surfaced. This does
  not provide a cross-process filesystem transaction or protection against a
  hostile process changing paths concurrently.

## Added capability

[Python dependency analysis](PYTHON_DEPENDENCY_ANALYSIS.md) covers declarations,
source APIs and wheel libraries through repository/inbox ingestion. It performs
no target code execution or dependency installation. The OpenSpec adoption record separates this verified static-analysis capability
from the broader physical-hardware deployment acceptance.

## Verification

- PASS: production image build, dependency/license gates and Java parser probe.
- PASS: full regression suite, 1,540 tests with 14 optional tests skipped.
- PASS: 17 focused Python/Wiki/runtime regressions, including malformed benchmark responses.
- PASS: real pinned GGUF CPU text and pixel-sensitive image vectors.
- PASS: isolated container setup, Python dependency search, readiness, UI/MCP,
  dependency validation and restart.
- PASS: deployment-kit image build, export and CPU Compose configuration.
- PASS: final `python3 harness.py check`, strict OpenSpec validation and artifact manifest.
- NOT RUN in this review: physical Windows/CUDA/Vulkan, native PyTorch model
  execution, cold model downloads, real PDF/OCR and remote GHCR publication.

Logs are local under `tmp/local/review-verification/`. Model checks reused cached
weights while still verifying hashes. Memory fit settings reserve free headroom;
they are not a strict GPU consumption cap. The broader
`ship-portable-oci-deployment` OpenSpec change remains active. No merge or push was
performed; dev artifacts become available only after a successful publishing run.

The final harness initially encountered host disk exhaustion during a rebuild.
After Docker released build cache and disk space recovered, it was rerun and
passed. Final rebuilt-container smoke also passed.

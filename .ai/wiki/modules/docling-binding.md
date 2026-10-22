---
id: modules.docling-binding
title: Real Docling PDF binding
kind: modules
status: active
summary: Production replacement for the synthesised Docling PDF stub. The real `docling.document_converter.DocumentConverter` parses PDFs; the real `docling.chunking.HybridChunker` aligns with the active embedding model tokenizer; the synthesised `_DoclingDocument` is reserved for unit tests only.
sourceRefs:
  - pi_platform/adapters/pdf/real_docling.py
  - pi_platform/adapters/pdf/docling_pdf_adapter.py
  - pi_platform/adapters/pdf/runtime_projection.py
  - tests/test_real_docling_binding.py
  - tests/test_pdf_production_mapping.py
  - tests/test_docling_production_binding.py
  - openspec/specs/2026-10-18-real-docling-pdf-adapter-and-hybrid-chunker/spec.md
maintenance:
  mode: authored
related:
  - modules.release-gate
  - modules.ingest
---

# Real Docling PDF binding

The platform MUST use the real `docling` package for PDF
ingestion in production. The synthesised `_DoclingDocument`
stub survives only in `tests/` paths and in unit-test mocks;
the production-capability gate refuses to accept the
synthesised path.

## Modules

- `pi_platform/adapters/pdf/real_docling.py` —
  - `RealDoclingConverter` lazily constructs the real
    `DocumentConverter` on first `convert()` and caches a
    `HybridChunkerAdapter` aligned with the active embedding
    model.
  - `HybridChunkerAdapter` / `HuggingFaceTokenizerAdapter`
    wrap the Docling vendor types and expose
    `count_tokens`, `encode`, `chunk` and
    `tokenizer_alignment`. Construction is best-effort so
    callers can inspect `tokenizer_alignment` without paying
    the model load cost; `count_tokens` / `chunk` raise
    `RealDoclingConverterError` when no usable inner was
    built.
  - `HuggingFaceTokenizerAdapter` prefers
    `AutoTokenizer.from_pretrained` and falls back to a
    config-sanitised load from the local Hugging Face cache
    (the recent `transformers` releases trip on the
    EmbeddingGemma `tokenizer_config` `extra_special_tokens`
    list bug; we strip it in a temp dir).
  - The caller's `max_tokens` budget is passed to the vendor
    Hugging Face tokenizer; alignment-only chunker construction is lazy.
  - Sanitized tokenizer copies use `TemporaryDirectory` and are removed
    on success and failure. The cache fallback honors Hugging Face cache
    environment settings and selects the hub's current local revision.
  - `_DEFAULT_TOKENIZER_FOR_MODEL` maps the two production
    embedding models; `PI_DOCLING_TOKENIZER` env var is the
    documented escape hatch for private mirrors.
  - `is_docling_available()` is the single signal the
    release gate reads.

- `pi_platform/adapters/pdf/docling_pdf_adapter.py` —
  `DoclingPdfAdapter` gains a `docling_converter=` injection
  point for tests and a `build_real_docling_pdf_adapter()`
  factory that refuses to construct when Docling is not installed.
  Direct construction also selects the real converter by default; fixtures
  must explicitly pass `allow_synthetic=True`. Conversion failures never
  synthesize content and partial vendor conversion status is rejected.
  Strategy `docling-pdf/v2-real` rejects legacy synthetic graph caches;
  rebuild those runtime caches before reusing an existing graph database.
  PDFium reads the authoritative page count and native text layers before
  conversion, so compressed page trees cannot silently truncate ingestion.
  Conversion owns bounded page windows, retains completed page checkpoints,
  and resumes failed windows. Mapped content preserves actual table cells,
  text labels, page geometry, figure PNG assets, source paths and anchors.
  Canonical section bodies contain real structural content.

- `pi_platform/adapters/pdf/docling_chunker.py` reconstructs vendor inputs
  only inside the PDF boundary and invokes the actual `HybridChunker`.
  Header context is included in table text through vendor contextualization;
  the tokenizer budgets that context. Anchors survive runtime splitting.
  A model switch leaves the neutral canonical graph unchanged.

## Vendor boundary

No `docling` import leaks past `pi_platform/adapters/pdf/`.
The release gate scans `pi_platform/core/canonical/` for any
import of the `docling` package — the static check fails if
any neutral canonical module references a vendor type by name.

## How to fix when something breaks

- **Token load trips `extra_special_tokens`** — the sanitised
  cache load strips the offending field. If the upstream
  `transformers` release fixes the bug, the
  `AutoTokenizer` branch wins and the temp-dir path is
  unused.
- **"max_tokens could not be determined automatically"** —
  the embedding model lacks a `sentence_bert_config.json`
  with `max_seq_length`. Either provide one, or set
  `PI_DOCLING_TOKENIZER` to an explicit tokenizer id.
- **Docling unavailable in the build** — install
  `pip install docling docling-core`; the factory raises
  `DoclingPdfAdapterError` at construction time otherwise,
  which is the documented behaviour.

## Verification boundary

`tests/test_pdf_production_mapping.py` exercises real vendor document/table/image
objects, actual HybridChunker with a local in-memory tokenizer, PDFium inspection
of a generated valid PDF, persisted assets and resume after conversion failure.
These tests do not download OCR/layout weights or claim full PDF layout inference;
that production acceptance gate requires separately available model assets.


## Pinned document assets

The adapter selects Heron layout, TableFormer V1 accurate tables and explicit
RapidOCR ONNX paths. Immutable upstream commits and separate weight licenses are
recorded in `distribution/licenses/model-licenses.json`; package MIT licenses
are recorded separately. This prevents Docling defaults from silently selecting
new models or a different OCR engine. `PI_DOCLING_CACHE` selects the artifact
cache; otherwise it follows the platform cache directory under
`projectexpert/docling`. First PDF use fetches only the selected revision files;
Hugging Face offline mode requires those files to exist already.

`tests/test_docling_production_binding.py` is the opt-in full inference suite:
100 native pages, a native table with a real chart image, and scanned PDF OCR.
Enable it with `PI_RUN_PDF_TESTS=1`. Missing models and inference errors fail
once enabled. `PdfStructuralChunker` preserves each canonical source unit and anchor.
`PdfRuntimeProjection` reuses one actual model-aligned HybridChunker per indexing
refresh to produce bounded runtime embedding segments. Canonical identifiers and
text remain unchanged; the semantic index stores a normalized mean of the segment
vectors under the canonical identifier. Projection policy and segment text
participate in the vector reuse hash. Tokenizer revisions match the pinned
embedding checkpoints; private mirrors can set `PI_DOCLING_TOKENIZER_REVISION`.

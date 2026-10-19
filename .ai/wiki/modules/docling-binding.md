---
id: modules.docling-binding
title: Real Docling PDF binding
kind: modules
status: active
summary: Production replacement for the synthesised Docling PDF stub. The real `docling.document_converter.DocumentConverter` parses PDFs; the real `docling.chunking.HybridChunker` aligns with the active embedding model tokenizer; the synthesised `_DoclingDocument` is reserved for unit tests only.
sourceRefs:
  - pi_platform/adapters/pdf/real_docling.py
  - pi_platform/adapters/pdf/docling_pdf_adapter.py
  - tests/test_real_docling_binding.py
  - openspec/changes/production-semantic-search-and-branch-reconciliation/specs/2026-10-18-real-docling-pdf-adapter-and-hybrid-chunker/spec.md
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
  - `max_tokens` is resolved from the embedding model's
    `sentence_bert_config.json` when available, else defaulted
    to 512.
  - `_DEFAULT_TOKENIZER_FOR_MODEL` maps the two production
    embedding models; `PI_DOCLING_TOKENIZER` env var is the
    documented escape hatch for private mirrors.
  - `is_docling_available()` is the single signal the
    release gate reads.

- `pi_platform/adapters/pdf/docling_pdf_adapter.py` —
  `DoclingPdfAdapter` gains a `docling_converter=` injection
  point for tests and a `build_real_docling_pdf_adapter()`
  factory that refuses to construct when Docling is not
  installed. The synthesised `_DoclingDocument` path remains
  as a fast test surface; production code paths use the
  factory.

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
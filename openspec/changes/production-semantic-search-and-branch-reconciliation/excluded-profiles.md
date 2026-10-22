# Production capability gate model boundaries

The embedding-model readiness probe selects inventory records with
`production_enabled=true`; it does not select by profile name. Other
capabilities have their own checks. License approval remains a separate gate
for every enabled component, including document-processing assets.

## Production-enabled set

| `model_id` | `profile` | Immutable revision |
|---|---|---|
| `google/embeddinggemma-2` | `semantic-cpu` | `914f7f89142e33e77833254d9c9b90c3cef7303b` |
| `Qwen/Qwen3-Embedding-0.6B` | `quality` | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` |

Both records have `production_enabled=true`. The runtime must load the real
binding for the selected model and satisfy its independent license policy.

## Excluded set

| `model_id` | Scope | Reason |
|---|---|---|
| `ggml-org/embeddinggemma-2-GGUF` | Optional pinned llama.cpp text/image runtime | Separate GGUF probe with model and projector hashes; excluded from in-process PyTorch probes, not disabled. |
| `Qwen/Qwen3-Embedding-0.6B-GGUF` | Optional pinned llama.cpp runtime | Separately probed through authenticated model identity and real vector checks; not part of the two in-process PyTorch probes. GPU hardware checks remain pending. |
| `hashing-1.0.0` | Explicit minimal profile | Deterministic diagnostic backend; never an implicit production semantic fallback. |
| `qwen3-reranker-0.6b` | Optional quality reranker | Placeholder excluded pending a separately verified binding. |
| `multimodal-figure-512` | Optional multimodal profile | Placeholder excluded pending a separately verified binding. |
| `tesseract-ocr` | Optional alternate OCR engine | Not selected by the pinned RapidOCR document path. |
| `paddleocr` | Optional alternate OCR engine | Not selected by the pinned RapidOCR document path. |
| `docling-project/docling-layout-heron` | Document layout asset | Real, pinned document-processing asset; not an embedding model. |
| `docling-project/docling-models` | Document table-structure asset | Real, pinned document-processing asset; not an embedding model. |
| `SWHL/RapidOCR` | Document OCR assets | Real, pinned document-processing assets; not an embedding model. |

The three document-asset records have `production_enabled=false` because that
field selects embedding probes, and `document_processing_enabled=true` because
the real PDF path uses them. They are not disabled or unimplemented. The PDF
adapter pins these revisions independently of the MIT Docling package license:

| Document model | Immutable revision | Inventoried asset license |
|---|---|---|
| `docling-project/docling-layout-heron` | `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8` | Apache-2.0 |
| `docling-project/docling-models` | `2199320848bb9a8a519d22e4b528185a4f9a6f64` | CDLA-Permissive-2.0 AND Apache-2.0 |
| `SWHL/RapidOCR` | `1cfba2e90fc938db55889873735088de210cc173` | Apache-2.0 |

## Updates

Update this file together with the model inventory and the actual model selector.
A real binding does not imply legal approval or inference readiness: execute the
corresponding opt-in production tests and retain their actual result. The PDF
suite uses `PI_RUN_PDF_TESTS=1`; load/inference errors fail once enabled.

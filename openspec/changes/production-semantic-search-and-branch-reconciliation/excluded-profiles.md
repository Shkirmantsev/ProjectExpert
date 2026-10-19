# Excluded production-capability-gate profile set

This file enumerates the model profiles that are explicitly
**excluded** from the `production-capability-gate` defined in
`openspec/changes/production-semantic-search-and-branch-reconciliation/specs/2026-10-18-production-capability-and-release-gates/spec.md`.

The gate checks records whose `profile` field is in the
**production-enabled set**; records whose `profile` is in the
**excluded set** are out of scope for the gate until the future
OpenSpec change that finishes their real binding.

## Production-enabled set

These profiles MUST have a real, pinned, non-`pinned-stub` record
in `distribution/licenses/model-licenses.json` for the gate to
pass.

| `model_id` | `profile` | Why production-enabled |
|---|---|---|
| `embeddinggemma2-512` | `semantic-cpu` | Selected by the `production` startup profile when the operator chooses `gemma`; covered by PR 3. |
| `qwen3-embedding-0.6b` | `quality` | Selected by the `production` startup profile when the operator chooses `qwen`; covered by PR 4. |
| `hashing-1.0.0` | `minimal` | Only selected by the explicit `minimal` startup profile; the gate treats `hashing-1.0.0` as a real-and-available record because the hashing adapter is the intended diagnostic backend, not a stub. |

## Excluded set

These profiles are part of the development roadmap and MUST NOT
cause the gate to fail while they remain `pinned-stub`. The
follow-up OpenSpec change that finishes their real binding MUST
remove the corresponding row from this list and add a PR 12
acceptance scenario that pins the real revision.

| `model_id` | `profile` | Why excluded | Follow-up change |
|---|---|---|---|
| `qwen3-reranker-0.6b` | `quality` | Reranker adapter is still a placeholder; finishing it is part of the post-v0.8 retrieval refinement roadmap, not this change. | Future `real-qwen3-reranker-binding` change. |
| `multimodal-figure-512` | `multimodal` | Multimodal figure binding is gated behind the `multimodal` profile; out of scope for the production semantic search hardening. | Future `real-multimodal-figure-binding` change. |
| `tesseract-ocr` | `documents-ocr` | OCR engine selection is part of the Docling / document processing follow-up; the `documents` profile is enabled by default and uses Docling's bundled OCR by default. | Future `real-docling-ocr-engine` change. |
| `paddleocr` | `documents-ocr` | Alternative OCR engine selection; same follow-up as Tesseract. | Future `real-docling-ocr-engine` change. |

## Update procedure

1. Edit this file when a profile transitions between the
   production-enabled and excluded sets.
2. Re-run `production-capability-gate` to confirm the gate now
   fails or passes as expected.
3. Update the acceptance scenario in
   `…/2026-10-18-production-capability-and-release-gates/spec.md`
   so it names the new boundary.

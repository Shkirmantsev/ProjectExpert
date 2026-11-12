#!/usr/bin/env python3
"""Release-only proof inside the exact production container on an internal network."""
import math
from pathlib import Path
import tempfile
import unittest

from pi_platform.deployment.offline_assets import configure


def main():
    configure(load_models=True)
    from tests.test_docling_production_binding import DoclingProductionBindingTests
    suite = unittest.TestSuite(DoclingProductionBindingTests(name) for name in (
        'test_native_table_cells_and_real_picture_are_mapped', 'test_scanned_pdf_uses_real_ocr'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit('Offline OCR/table/figure conversion failed')
    from pi_platform.adapters.retrieval.llama_cpp_embedding_model import LlamaCppEmbeddingModel
    from pi_platform.ports.retrieval.embedding_model import EmbeddingRequest, EmbeddingRole
    from pi_platform.adapters.pdf.real_docling import HuggingFaceTokenizerAdapter
    # This eagerly loads the complete local tokenizer, beyond mere file presence.
    import os
    tokenizer = HuggingFaceTokenizerAdapter(tokenizer_id=os.environ['PI_DOCLING_TOKENIZER'])
    assert tokenizer.count_tokens('Offline tokenizer segmentation') > 0
    model = LlamaCppEmbeddingModel()
    vectors = model.embed_requests([
        EmbeddingRequest('ledger ' * 1500, EmbeddingRole.DOCUMENT),
        EmbeddingRequest('billing', EmbeddingRole.QUERY)])
    from PIL import Image
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / 'pixels.png'
        for color in ('red', 'blue'):
            Image.new('RGB', (64, 64), color).save(path)
            vectors.append(model.embed_request(EmbeddingRequest('colored square', EmbeddingRole.DOCUMENT, image_path=str(path))))
    assert all(len(vector) == 512 and math.isclose(sum(x*x for x in vector), 1, abs_tol=1e-5) for vector in vectors)
    assert sum(x*y for x,y in zip(vectors[-2], vectors[-1])) < .999
    from pi_platform.adapters.retrieval.embeddinggemma2_embedding_model import EmbeddingGemma2EmbeddingModel
    native = EmbeddingGemma2EmbeddingModel()
    native_vectors = native.embed_requests([
        EmbeddingRequest('offline torch billing', EmbeddingRole.DOCUMENT)])
    assert len(native_vectors) == 1 and len(native_vectors[0]) == 512
    assert all(math.isfinite(value) for value in native_vectors[0])
    print('PASS: offline OCR, tables, figures, tokenizer, wide text/query, native torch and pixel-sensitive image embeddings')


if __name__ == '__main__':
    main()

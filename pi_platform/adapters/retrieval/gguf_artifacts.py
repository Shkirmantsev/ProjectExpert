"""Pinned upstream assets for the optional llama.cpp embedding runtime."""
MODEL_ID = 'Qwen/Qwen3-Embedding-0.6B-GGUF'
REVISION = '370f27d7550e0def9b39c1f16d3fbaa13aa67728'
FILENAME = 'Qwen3-Embedding-0.6B-Q8_0.gguf'
SHA256 = '06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439'
MODEL_ALIAS = 'project-intelligence-qwen3-q8-' + SHA256
MODEL_URL = f'https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{FILENAME}'
RUNTIME_VERSION = 'b11515'

# Official llama.cpp conversion of EmbeddingGemma 2, including its projector.
GEMMA_MODEL_ID = 'ggml-org/embeddinggemma-2-GGUF'
GEMMA_REVISION = '58faf90940886df2d62be555c8765d00dac362c5'
GEMMA_FILENAME = 'embeddinggemma-2-Q8_0.gguf'
GEMMA_SHA256 = '2188ac1deca4b77dffefd603c2776a9d76d9d74ec01841392982ebb840b09135'
GEMMA_PROJECTOR_FILENAME = 'mmproj-embeddinggemma-2-Q8_0.gguf'
GEMMA_PROJECTOR_SHA256 = 'c4a8a52691ecef40618438928bdf9e68379b854e24166f292592353db0aab64f'
GEMMA_MODEL_ALIAS = 'project-intelligence-gemma2-q8-' + GEMMA_SHA256 + '-' + GEMMA_PROJECTOR_SHA256
GEMMA_URL_ROOT = f'https://huggingface.co/{GEMMA_MODEL_ID}/resolve/{GEMMA_REVISION}/'

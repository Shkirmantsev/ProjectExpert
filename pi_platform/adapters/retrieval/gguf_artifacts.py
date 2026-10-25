"""Pinned upstream assets for the optional llama.cpp embedding runtime."""
MODEL_ID = 'openmycel/Qwen3-Embedding-0.6B-GGUF'
REVISION = '333bba6d067e5ab591bc8c21f1b15950e4435083'
FILENAME = 'Qwen3-Embedding-0.6B-Q4_K_M.gguf'
SHA256 = '23d234bb57a42528a22a13e7beb8b57d8844b2b9cc741b4c27a8ff132abf0dfd'
MODEL_ALIAS = 'project-intelligence-qwen3-q4-' + SHA256
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

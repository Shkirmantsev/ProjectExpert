"""Pinned upstream assets for the portable EmbeddingGemma 2 inference runtime.

ProjectExpert ships exactly one production embedding model: EmbeddingGemma 2
in the ``Q8_0`` quantisation, together with the matching ``Q8_0`` multimodal
projector. Both artefacts are pinned by repository, revision and SHA-256 and
are downloaded only by an explicit setup step; nothing is fetched implicitly
at runtime.

Source of truth: the official ``ggml-org`` conversion of the upstream
``google/embeddinggemma-2`` checkpoint. The upstream checkpoint itself is
published in the Transformers format and therefore cannot be executed by the
portable ``llama.cpp`` runtime used on Windows and Linux.
"""

__all__ = [
    "GEMMA_MODEL_ID",
    "GEMMA_REVISION",
    "GEMMA_FILENAME",
    "GEMMA_SHA256",
    "GEMMA_PROJECTOR_FILENAME",
    "GEMMA_PROJECTOR_SHA256",
    "GEMMA_MODEL_ALIAS",
    "GEMMA_URL_ROOT",
    "GEMMA_QUANTIZATION",
    "GEMMA_POOLING",
    "GEMMA_FULL_DIMENSION",
    "GEMMA_INDEX_DIMENSION",
    "GEMMA_INSTRUCTION_PROFILE",
    "RUNTIME_VERSION",
]


# -- Pinned EmbeddingGemma 2 artefacts -----------------------------------
#
# Verified against https://huggingface.co/api/models/ggml-org/embeddinggemma-2-GGUF
# (revision 58faf90940886df2d62be555c8765d00dac362c5) and by downloading and
# hashing both files. Do not change a checksum without re-verifying the file.
GEMMA_MODEL_ID = "ggml-org/embeddinggemma-2-GGUF"
GEMMA_REVISION = "58faf90940886df2d62be555c8765d00dac362c5"
GEMMA_FILENAME = "embeddinggemma-2-Q8_0.gguf"
GEMMA_SHA256 = "2188ac1deca4b77dffefd603c2776a9d76d9d74ec01841392982ebb840b09135"
GEMMA_PROJECTOR_FILENAME = "mmproj-embeddinggemma-2-Q8_0.gguf"
GEMMA_PROJECTOR_SHA256 = "c4a8a52691ecef40618438928bdf9e68379b854e24166f292592353db0aab64f"
GEMMA_URL_ROOT = (
    f"https://huggingface.co/{GEMMA_MODEL_ID}/resolve/{GEMMA_REVISION}/"
)

# The alias is the identity the runtime publishes through ``/v1/models``. It
# embeds both checksums so a swapped backbone or projector can never be
# mistaken for the pinned pair.
GEMMA_MODEL_ALIAS = (
    "project-intelligence-gemma2-q8-" + GEMMA_SHA256 + "-" + GEMMA_PROJECTOR_SHA256
)

# -- Model geometry -------------------------------------------------------
#
# The runtime returns 768 dimensions with mean pooling and L2 normalisation.
# The platform stores a Matryoshka-truncated 512-dimensional vector and
# re-normalises it after truncation. Both values participate in the profile
# identity so a change of either forces a new vector namespace.
GEMMA_QUANTIZATION = "Q8_0"
GEMMA_POOLING = "mean"
GEMMA_FULL_DIMENSION = 768
GEMMA_INDEX_DIMENSION = 512
GEMMA_INSTRUCTION_PROFILE = "project-expert-gemma-search-v3"

# -- Runtime ---------------------------------------------------------------
#
# Pinned llama.cpp release. The deployment uses the matching official
# runtime images and the matching native release archives.
RUNTIME_VERSION = "b11515"

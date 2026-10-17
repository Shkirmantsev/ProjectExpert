"""Hashing embedding fallback smoke tests (Change Package C4).

Guards the minimal-profile invariant: ``HashingEmbeddingModel`` stays
the default zero-dependency embedding backend. The module-import
check proves the adapter pulls in only stdlib + ``pi_platform`` —
no ``numpy``, ``torch``, ``sentence_transformers`` or ``usearch``.
"""

from __future__ import annotations

import ast
import importlib
import math
import unittest
from pathlib import Path

from pi_platform.adapters.retrieval.hashing_embedding_model import (
    HashingEmbeddingAdapter,
)
from pi_platform.core.retrieval.embedding_model import (
    HASHING_DEFAULT_DIMENSION,
    HASHING_DEFAULT_VERSION,
    HASHING_LICENSE_ID,
    HashingEmbeddingModel,
)


BANNED_IMPORTS = frozenset(
    {"numpy", "torch", "sentence_transformers", "usearch"}
)

_MODULE_PATHS = (
    "pi_platform.core.retrieval.embedding_model",
    "pi_platform.adapters.retrieval.hashing_embedding_model",
)


class HashingEmbeddingFallbackTests(unittest.TestCase):
    def test_hashing_dimensions_384(self):
        self.assertEqual(HashingEmbeddingModel().dimension(), 384)
        self.assertEqual(HASHING_DEFAULT_DIMENSION, 384)
        self.assertEqual(HashingEmbeddingAdapter().dimension(), 384)

    def test_hashing_deterministic(self):
        model = HashingEmbeddingModel()
        text = "Where is ILO-5193 implemented?"
        self.assertEqual(model.embed(text), model.embed(text))
        batch = model.embed_batch([text, "other text"])
        self.assertEqual(batch[0], model.embed(text))

    def test_hashing_zero_norm_for_empty_text(self):
        vector = HashingEmbeddingModel().embed("")
        self.assertEqual(len(vector), 384)
        norm = math.sqrt(sum(x * x for x in vector))
        self.assertLess(norm, 1e-9)

    def test_hashing_model_version(self):
        self.assertEqual(HashingEmbeddingModel().model_version(), "hashing-1.0.0")
        self.assertEqual(HASHING_DEFAULT_VERSION, "hashing-1.0.0")
        self.assertEqual(HashingEmbeddingAdapter().model_version(), "hashing-1.0.0")

    def test_hashing_license(self):
        self.assertEqual(HashingEmbeddingModel().license_id(), "Apache-2.0")
        self.assertEqual(HASHING_LICENSE_ID, "Apache-2.0")

    def test_hashing_no_external_deps(self):
        for module_name in _MODULE_PATHS:
            module = importlib.import_module(module_name)
            source = Path(module.__file__).read_text(encoding="utf-8")
            tree = ast.parse(source)
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(
                        alias.name.split(".")[0] for alias in node.names
                    )
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.level == 0:
                        imported.add(node.module.split(".")[0])
            banned = imported & BANNED_IMPORTS
            self.assertFalse(
                banned,
                f"{module_name} imports banned modules: {sorted(banned)}",
            )
            # Every non-stdlib top-level import must come from this repo.
            self.assertIn("pi_platform", {name.split(".")[0] for name in imported})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

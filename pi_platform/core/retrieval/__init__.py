"""Default Phase 4 retrieval core implementations.

The :mod:`pi_platform.core.retrieval` package holds language-
neutral default implementations that the production adapters
compose. Backend-specific embedding / reranker / ColBERT-style
runtime libraries live under :mod:`pi_platform.adapters.retrieval`
so the core stays lightweight and CPU-only on a stdlib-only
machine.
"""

from __future__ import annotations


__all__: list[str] = []
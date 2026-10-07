"""Default Phase 5 orchestration core implementations.

The :mod:`pi_platform.core.orchestration` package holds
language-neutral default implementations that the production
adapters compose. Backend-specific LLM runtimes live under
:mod:`pi_platform.adapters.orchestration` so the core stays
lightweight and the default container ships without a model
binding.
"""

from __future__ import annotations


__all__: list[str] = []
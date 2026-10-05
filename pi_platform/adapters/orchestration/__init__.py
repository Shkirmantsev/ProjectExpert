"""Phase 5 orchestration adapters for the v0.8 Project
Intelligence Platform.

The adapter layer binds the Phase 5 core to concrete
backends: stub local LLM, default query orchestrator,
default task context builder and default capability
discovery. The default container ships with the stub LLM
only; opt-in LLM backends land as additional adapters
when the corresponding Python package is installed.
"""

from __future__ import annotations


__all__: list[str] = []
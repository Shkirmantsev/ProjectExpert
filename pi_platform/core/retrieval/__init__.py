"""Default Phase 4 retrieval core implementations.

The :mod:`pi_platform.core.retrieval` package holds language-
neutral default implementations that the production adapters
compose. Backend-specific embedding / reranker / ColBERT-style
runtime libraries live under :mod:`pi_platform.adapters.retrieval`
so the core stays lightweight and CPU-only on a stdlib-only
machine.

The v0.8 refinement (OpenSpec change
``improve-ingestion-retrieval-local-models``, Change Package A)
adds additive types (:class:`QueryFeatures`, the
:class:`SelectionPort` / :class:`SelectionCore` and
:class:`RetrievalTrace` value objects) without changing the
existing public surface.
"""

from __future__ import annotations


__all__: list[str] = [
    "QueryFeatures",
    "SelectionCore",
    "SelectionPort",
    "SelectionState",
    "SelectionResult",
    "CandidateTrace",
    "RetrievalTrace",
    "RetrievalTraceBuilder",
]


def __getattr__(name: str):  # pragma: no cover - import indirection
    """Lazy public re-exports to avoid import cycles.

    Importing the new retrieval v0.8-refinement types at module
    load time would create a cycle through
    :mod:`pi_platform.core.retrieval.hybrid_retrieval`, which in
    turn depends on :class:`QueryFeatures` under
    :data:`typing.TYPE_CHECKING`. Resolving the re-exports lazily
    keeps the legacy import order intact.
    """

    if name == "QueryFeatures":
        from pi_platform.core.retrieval.query_features import QueryFeatures
        return QueryFeatures
    if name in {
        "SelectionCore",
        "SelectionPort",
        "SelectionState",
        "SelectionResult",
        "CandidateTrace",
    }:
        from pi_platform.core.retrieval import selection as _selection
        from pi_platform.ports.retrieval import selection as _port
        return {
            "SelectionCore": _selection.SelectionCore,
            "SelectionPort": _port.SelectionPort,
            "SelectionState": _port.SelectionState,
            "SelectionResult": _port.SelectionResult,
            "CandidateTrace": _port.CandidateTrace,
        }[name]
    if name in {"RetrievalTrace", "RetrievalTraceBuilder"}:
        from pi_platform.core.retrieval.retrieval_trace import (
            RetrievalTrace,
            RetrievalTraceBuilder,
        )
        return {
            "RetrievalTrace": RetrievalTrace,
            "RetrievalTraceBuilder": RetrievalTraceBuilder,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
"""Retrieval trace value object for the v0.8 refinement.

Implements the retrieval-trace delta spec from the
``improve-ingestion-retrieval-local-models`` change package
(Change Package A5): a frozen, JSON-serialisable
:class:`RetrievalTrace` attached to
:class:`~pi_platform.ports.retrieval.multi_stage_retrieval.RetrievalResult`
that makes retrieval failures debuggable without leaking secret
metadata.

The trace is optional in the normal API response (controlled by
``RetrievalQuery.include_trace``), always available in debug /
evaluation mode, and redacted through the existing secret provider
before serialisation. When the secret provider is unavailable the
serialiser surfaces a visible ``WARNING`` budget decision instead of
failing silently.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from typing import Callable, Optional


__all__ = [
    "RetrievalTrace",
    "RetrievalTraceBuilder",
]


# Module-level secret provider used by :meth:`RetrievalTraceBuilder.to_json`.
# The construction is deferred to import time (not call time) so the
# module stays import-light; the broad ``Exception`` catch covers both
# ``ImportError`` (a stripped deployment without the control package) and
# ``RuntimeError`` (a misconfigured environment). When available the
# redaction callable is the bound ``DefaultSecretProvider.redact`` method,
# which replaces every previously resolved secret value with its
# documented redacted reference form. When unavailable the serialiser
# surfaces a visible ``WARNING`` budget decision instead of failing
# silently.
try:
    from pi_platform.ports.control.secrets import SecretProviderPort
    from pi_platform.core.control.secrets import DefaultSecretProvider

    _SECRET_PROVIDER: Optional[SecretProviderPort] = DefaultSecretProvider()
    _redact_callable: Optional[Callable[..., str]] = _SECRET_PROVIDER.redact
except Exception:  # pragma: no cover - defensive import guard
    _SECRET_PROVIDER = None
    _redact_callable = None


_REDACTION_CONTEXT = "retrieval-trace"


@dataclass(frozen=True)
class RetrievalTrace:
    """Immutable per-retrieval explanation record.

    Every field is optional and defaults to an empty value so a
    partially populated trace (for example from a pipeline stage that
    failed early) is still a valid object. ``timings`` is a tuple of
    ``(stage, milliseconds)`` pairs rather than a mapping so the
    frozen value serialises deterministically.
    """

    query_features: object = None
    active_filters: object = None
    exact_candidates: tuple[str, ...] = ()
    dense_candidates: tuple[str, ...] = ()
    sparse_candidates: tuple[str, ...] = ()
    fusion: object = None
    reranker: object = None
    selection: object = None
    graph_expansion: object = None
    hierarchy_expansion: object = None
    budget_decisions: tuple[str, ...] = ()
    timings: tuple[tuple[str, int], ...] = ()


class RetrievalTraceBuilder:
    """Mutable builder for the frozen :class:`RetrievalTrace`.

    The multi-stage pipeline populates the trace from data it has
    already computed; the builder itself contains no retrieval
    business logic. ``set`` / ``add_timing`` / ``add_budget_decision``
    return ``self`` so calls can be chained.
    """

    #: Section names accepted by :meth:`set`.
    SECTIONS = frozenset({
        "query_features",
        "active_filters",
        "exact_candidates",
        "dense_candidates",
        "sparse_candidates",
        "fusion",
        "reranker",
        "selection",
        "graph_expansion",
        "hierarchy_expansion",
    })

    def __init__(self) -> None:
        self._sections: dict[str, object] = {}
        self._budget_decisions: list[str] = []
        self._timings_ms: dict[str, int] = {}

    def set(self, section: str, value: object) -> "RetrievalTraceBuilder":
        """Set a trace ``section`` to ``value`` and return the builder."""
        if section not in self.SECTIONS:
            raise ValueError(
                f"unknown RetrievalTrace section: {section!r}; "
                f"expected one of {sorted(self.SECTIONS)}"
            )
        self._sections[section] = value
        return self

    def add_timing(
        self, stage: str, ms: int,
    ) -> "RetrievalTraceBuilder":
        """Record ``ms`` milliseconds for ``stage`` (summed per stage)."""
        self._timings_ms[stage] = self._timings_ms.get(stage, 0) + int(ms)
        return self

    def add_budget_decision(
        self, reason: str,
    ) -> "RetrievalTraceBuilder":
        """Append a human-readable budget decision to the trace."""
        self._budget_decisions.append(str(reason))
        return self

    def build(self) -> RetrievalTrace:
        """Materialise the frozen :class:`RetrievalTrace`."""
        timings = tuple(
            (stage, self._timings_ms[stage])
            for stage in sorted(self._timings_ms)
        )
        return RetrievalTrace(
            query_features=self._sections.get("query_features"),
            active_filters=self._sections.get("active_filters"),
            exact_candidates=tuple(
                self._sections.get("exact_candidates") or (),
            ),
            dense_candidates=tuple(
                self._sections.get("dense_candidates") or (),
            ),
            sparse_candidates=tuple(
                self._sections.get("sparse_candidates") or (),
            ),
            fusion=self._sections.get("fusion"),
            reranker=self._sections.get("reranker"),
            selection=self._sections.get("selection"),
            graph_expansion=self._sections.get("graph_expansion"),
            hierarchy_expansion=self._sections.get("hierarchy_expansion"),
            budget_decisions=tuple(self._budget_decisions),
            timings=timings,
        )

    def to_json(self) -> str:
        """Serialise the trace to a deterministic JSON string.

        Tuples become lists, dataclasses become dicts and sets become
        sorted lists; keys are sorted and separators are compact so
        the output is byte-stable. Every string value is passed
        through the secret-provider redaction filter. When the secret
        provider is unavailable a visible ``WARNING`` budget decision
        is prepended to the trace so the gap is observable instead of
        silent.
        """
        trace = self.build()
        if _redact_callable is None:
            trace = dataclasses.replace(
                trace,
                budget_decisions=(
                    "WARNING: secret_provider unavailable",
                ) + tuple(trace.budget_decisions),
            )
        payload = self._redact_value(trace)
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
        )

    def _redact_value(self, value: object) -> object:
        """Redact ``value`` through the module-level secret provider.

        Strings are redacted in place via
        ``SecretProviderPort.redact(value, context="retrieval-trace")``.
        Non-string containers (dicts, lists, tuples, sets) are walked
        recursively so only string leaves are redacted. When the
        provider is unavailable the value is returned unchanged; the
        caller already recorded the visible ``WARNING`` budget decision.
        """
        if isinstance(value, str):
            if _redact_callable is None:
                return value
            try:
                return str(_redact_callable(
                    value, context=_REDACTION_CONTEXT,
                ))
            except Exception:
                return value
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {
                f.name: self._redact_value(getattr(value, f.name))
                for f in dataclasses.fields(value)
            }
        if isinstance(value, dict):
            return {
                str(k): self._redact_value(v) for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._redact_value(v) for v in value]
        if isinstance(value, (set, frozenset)):
            return [self._redact_value(v) for v in sorted(value, key=repr)]
        return value

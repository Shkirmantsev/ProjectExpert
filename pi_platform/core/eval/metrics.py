"""Phase 10 §49 deterministic metric schema `phase-10-eval/1`.

The :class:`EvalReport` value type is the structured output of every
Phase 10 scenario. It is intentionally serialisable to JSON and is
written atomically to ``tmp/local/project-context/eval/last.json``
through :func:`pi_platform.core.eval.writer.write_atomic`.

The schema is fixed for v1.0 and is referenced from the
``integration-quality-gates`` capability spec
(``openspec/specs/2026-10-12-integration-quality-gates/spec.md``).
Modifying the schema requires bumping the ``SCHEMA_VERSION`` constant
and recording the bump in an ADR.
"""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Mapping


SCHEMA_VERSION = "phase-10-eval/1"


@dataclass(frozen=True)
class MetricSchema:
    """The schema descriptor embedded in every metric file."""

    name: str
    version: str

    def as_dict(self) -> dict:
        return {"name": self.name, "version": self.version}


@dataclass
class EvalMetrics:
    """Mutable metrics accumulator used by individual scenarios."""

    # Retrieval
    retrieval_recall_k: float = 0.0
    retrieval_precision_k: float = 0.0
    # Reranker
    reranker_quality: float = 0.0
    # Context
    context_bytes: int = 0
    context_tokens_in: int = 0
    context_tokens_out: int = 0
    context_soft_cap_exceeded: bool = False
    # External LLM
    llm_external_tokens: int = 0
    # Latency
    latency_retrieve_p95_ms: int = 0
    latency_delegate_p95_ms: int = 0
    # Cache reuse
    cache_reuse_rate: float = 0.0
    # Branch switch
    branch_switch_hydration_ms: int = 0
    # Stale knowledge detection
    stale_detection_rate: float = 0.0
    # Plugin lifecycle
    plugin_setup_success_rate: float = 0.0
    # OKF conformance
    okf_pass_rate: float = 0.0
    okf_fail_rate_by_reason: Mapping[str, int] = field(default_factory=dict)
    # Round trip
    round_trip_unchanged_diff_bytes: int = 0
    # Counters for invariant probes
    invariants_run: int = 0
    invariants_passed: int = 0
    invariants_failed: int = 0
    invariants_failed_labels: tuple[str, ...] = ()

    def update(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if not hasattr(self, k):
                raise AttributeError(f"Unknown metric field: {k!r}")
            setattr(self, k, v)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["okf_fail_rate_by_reason"] = dict(self.okf_fail_rate_by_reason)
        return d


@dataclass
class EvalReport:
    """Structured output of a Phase 10 evaluation run.

    Stable JSON serialisable representation. `timestamp` is the
    scenario-start time and is the only field that may differ between
    re-runs against the same inputs.
    """

    schema: MetricSchema
    scope: str
    timestamp: float
    metrics: EvalMetrics
    extra: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        out = {
            "schema": self.schema.as_dict(),
            "scope": self.scope,
            "timestamp": self.timestamp,
            "metrics": self.metrics.to_dict(),
        }
        if self.extra:
            out["extra"] = dict(self.extra)
        return out


def now() -> float:
    """A monotonic, second-precision timestamp suitable for report files."""
    return time.time()


def collect(scope: str, metrics: EvalMetrics, *, extra: Mapping[str, Any] | None = None) -> EvalReport:
    """Build a fresh :class:`EvalReport` for ``scope``.

    ``scope`` is the change ID or scenario identifier the report
    describes. ``metrics`` is the caller-managed accumulator; the
    report snapshots its current state.
    """
    schema = MetricSchema(name="phase-10-eval", version=SCHEMA_VERSION.replace("phase-10-eval/", ""))
    return EvalReport(
        schema=schema,
        scope=scope,
        timestamp=now(),
        metrics=dataclasses.replace(metrics),
        extra=dict(extra or {}),
    )

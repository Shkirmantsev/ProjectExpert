"""Documented bounds for `phase-10-eval/1` metric values.

The metrics gate (`make metrics-gate`) validates the ``metrics``
object of ``tmp/local/project-context/eval/last.json`` against the
bounds below. Every bound here is justified by the *semantics of the
field itself* — no invented numeric performance targets are encoded
(thresholds such as "recall >= 0.95" are operator policy, not domain
logic, and are deliberately not enforced here):

- **Rates / proportions** live in ``[0.0, 1.0]``: a rate, recall,
  precision or quality score cannot be negative nor exceed 100%.
- **Counters** (bytes, tokens, milliseconds, counts) are
  **non-negative**: ``>= 0``.
- ``okf_fail_rate_by_reason`` values are per-reason counters:
  ``>= 0``.
- ``invariants_passed <= invariants_run``: the passed set is a subset
  of the executed set.
- Documented non-numeric fields (``context_soft_cap_exceeded`` bool,
  ``invariants_failed_labels`` string list) are type-checked instead.

Only fields documented by
:class:`pi_platform.core.eval.metrics.EvalMetrics` are validated;
unknown extra keys are ignored so the schema can grow without breaking
the gate. Absent fields are not violations — the gate bounds values
that are present rather than mandating a fixed key set.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


# Rate/proportion fields: bounded to [0.0, 1.0].
RATE_BOUNDS: dict[str, tuple[float, float]] = {
    "retrieval_recall_k": (0.0, 1.0),
    "retrieval_precision_k": (0.0, 1.0),
    "reranker_quality": (0.0, 1.0),
    "cache_reuse_rate": (0.0, 1.0),
    "stale_detection_rate": (0.0, 1.0),
    "plugin_setup_success_rate": (0.0, 1.0),
    "okf_pass_rate": (0.0, 1.0),
}

# Non-negative counters: bytes, tokens, milliseconds, counts.
NONNEGATIVE_COUNTERS: tuple[str, ...] = (
    "context_bytes",
    "context_tokens_in",
    "context_tokens_out",
    "llm_external_tokens",
    "latency_retrieve_p95_ms",
    "latency_delegate_p95_ms",
    "branch_switch_hydration_ms",
    "round_trip_unchanged_diff_bytes",
    "invariants_run",
    "invariants_passed",
    "invariants_failed",
)

# Documented mapping of per-reason counters.
REASON_COUNTER_MAP = "okf_fail_rate_by_reason"

# Documented non-numeric fields, validated by type instead of bounds.
BOOL_FIELDS: tuple[str, ...] = ("context_soft_cap_exceeded",)
STRING_LIST_FIELDS: tuple[str, ...] = ("invariants_failed_labels",)


def _is_number(value: Any) -> bool:
    # bool is an int subclass in Python; a flag is not a metric number.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return repr(value)


@dataclass(frozen=True)
class BoundViolation:
    """One metric that violates its documented bound."""

    metric: str
    value: Any
    expected: str
    reason: str

    def as_dict(self) -> dict:
        return {
            "metric": self.metric,
            "value": _jsonable(self.value),
            "expected": self.expected,
            "reason": self.reason,
        }


def _check_number(
    metrics: Mapping[str, Any], name: str, low: float, high: float | None
) -> list[BoundViolation]:
    if name not in metrics:
        return []
    value = metrics[name]
    expected = (
        f"number in [{low}, {high}]" if high is not None else f"number >= {low}"
    )
    if not _is_number(value):
        return [BoundViolation(name, value, expected, "type")]
    if not math.isfinite(value):
        return [BoundViolation(name, value, expected, "not-finite")]
    if value < low:
        return [BoundViolation(name, value, expected, "below-min")]
    if high is not None and value > high:
        return [BoundViolation(name, value, expected, "above-max")]
    return []


def validate_metrics(metrics: Any) -> list[BoundViolation]:
    """Return every documented bound violation in a ``metrics`` object.

    A non-mapping ``metrics`` value yields a single violation named
    ``"metrics"``. The returned list is deterministic (fixed field
    order) so identical inputs produce identical output.
    """
    if not isinstance(metrics, Mapping):
        return [BoundViolation("metrics", metrics, "object", "type")]

    violations: list[BoundViolation] = []
    for name, (low, high) in RATE_BOUNDS.items():
        violations.extend(_check_number(metrics, name, low, high))
    for name in NONNEGATIVE_COUNTERS:
        violations.extend(_check_number(metrics, name, 0.0, None))

    if REASON_COUNTER_MAP in metrics:
        reasons = metrics[REASON_COUNTER_MAP]
        if not isinstance(reasons, Mapping):
            violations.append(
                BoundViolation(REASON_COUNTER_MAP, reasons, "object", "type")
            )
        else:
            # Per-reason counters are non-negative; the reported metric
            # name is namespaced so the offending reason is machine-readable.
            for reason in list(reasons):
                for violation in _check_number(reasons, reason, 0.0, None):
                    violations.append(
                        BoundViolation(
                            f"{REASON_COUNTER_MAP}.{violation.metric}",
                            violation.value,
                            violation.expected,
                            violation.reason,
                        )
                    )

    for name in BOOL_FIELDS:
        if name in metrics and not isinstance(metrics[name], bool):
            violations.append(
                BoundViolation(name, metrics[name], "bool", "type")
            )
    for name in STRING_LIST_FIELDS:
        if name not in metrics:
            continue
        value = metrics[name]
        if not isinstance(value, (list, tuple)) or not all(
            isinstance(item, str) for item in value
        ):
            violations.append(
                BoundViolation(name, value, "list of strings", "type")
            )

    # The passed set is a subset of the executed set.
    run = metrics.get("invariants_run")
    passed = metrics.get("invariants_passed")
    if (
        "invariants_run" in metrics
        and "invariants_passed" in metrics
        and _is_number(run)
        and _is_number(passed)
        and passed > run
    ):
        violations.append(
            BoundViolation(
                "invariants_passed",
                passed,
                f"number <= invariants_run ({run})",
                "above-max",
            )
        )
    return violations
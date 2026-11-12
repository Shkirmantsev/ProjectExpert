"""Stage-specific resource policy driven by validated throughput evidence.

No probes or benchmarks happen here. Callers supply evidence from the same
workload/runtime identity; absent evidence produces an explicit fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


@dataclass(frozen=True)
class StageResourceEvidence:
    stage: str
    backend: str
    runtime_identity: str
    workload_identity: str
    completed_per_second: tuple[float, ...] = ()
    supported: bool = True
    healthy: bool = True
    memory_admitted: bool = True
    quality_validated: bool = True
    physical_devices: tuple[str, ...] = ()
    quality_reason: str = ""


@dataclass(frozen=True)
class StageResourceDecision:
    stage: str
    backend: str
    reason: str
    evidence_state: str
    rejected: tuple[tuple[str, str], ...] = ()


class StageResourcePlanner:
    """Choose only real implementations for each independently measured stage.

    A backend may represent a hybrid only if the caller has measured that
    combination and validated its quality and physical-device identities.
    Overlapping sample ranges are inconclusive; accelerator preference breaks
    such ties without inventing a ten-percent minimum improvement.
    """

    def select(
        self, stage: str, candidates: Sequence[StageResourceEvidence], *,
        runtime_identity: str, workload_identity: str,
    ) -> StageResourceDecision:
        valid = []
        rejected = []
        for item in candidates:
            if item.stage != stage:
                continue
            reason = None
            if not item.supported:
                reason = "unsupported implementation"
            elif not item.healthy:
                reason = "unhealthy backend"
            elif not item.memory_admitted:
                reason = "insufficient memory"
            elif not item.quality_validated:
                reason = item.quality_reason or "quality or parity not validated"
            elif len(set(item.physical_devices)) != len(item.physical_devices):
                reason = "duplicate physical device"
            elif (item.runtime_identity != runtime_identity
                  or item.workload_identity != workload_identity):
                reason = "stale or incompatible evidence"
            elif (len(item.completed_per_second) < 3
                  or any(not math.isfinite(value) or value <= 0
                         for value in item.completed_per_second)):
                reason = "insufficient repeated throughput evidence"
            if reason:
                rejected.append((item.backend, reason))
            else:
                valid.append(item)
        if not valid:
            return StageResourceDecision(stage, "cpu", "no comparable validated evidence; cpu fallback",
                                         "unavailable", tuple(rejected))
        # Deterministic ordering independent of probe completion order.
        valid.sort(key=lambda item: (item.backend == "cpu", item.backend))
        chosen = max(valid, key=lambda item: sum(item.completed_per_second) / len(item.completed_per_second))
        contenders = [item for item in valid
                      if max(item.completed_per_second) >= min(chosen.completed_per_second)]
        inconclusive = len(contenders) > 1
        if inconclusive:
            chosen = contenders[0]
        return StageResourceDecision(
            stage, chosen.backend,
            "overlapping throughput samples; deterministic accelerator preference" if inconclusive
            else "highest validated completed work per second",
            "inconclusive" if inconclusive else "measured", tuple(rejected),
        )

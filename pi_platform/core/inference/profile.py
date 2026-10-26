"""The inference runtime selection policy.

Pure function, no I/O, fully unit-testable without hardware.

THE POLICY (spec ``portable-inference-runtime``):

* The CPU baseline is always valid and is the final fallback.
* Candidates are evaluated in ``prefer`` order.
* A candidate is REJECTED when:
    - ``candidate.ok`` is False               -> ``"probe failed"``
    - no device of that backend was found     -> ``"no device reported"``
    - every device of that backend is a
      software rasteriser                     -> ``"software device only"``
    - the backend is not in ``prefer``        -> ``"backend not preferred"``
    - ``allow_integrated`` is False and the
      only usable devices are integrated      -> ``"integrated device not allowed"``
* Among the valid devices of the selected backend pick the FIRST one,
  unless a device with a usable memory reading exists, in which case
  prefer it.
* ``fit_target_mib = min(512, max(192, round(reported_free_mib * 0.35)))``
  when a memory reading is available, otherwise ``default_fit_target_mib``.
* Every rejected candidate is recorded with its reason.

The CPU baseline is special: the CPU probe reports no *devices* (the
runtime prints ``(none)``) because CPU-only execution deliberately disables
device use. A successful CPU candidate is therefore always a valid CPU
profile with ``device=None`` and is never rejected for "no device reported".

An unavailable or unusable GPU degrades to the validated CPU profile. The
policy never signals a GPU failure as fatal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .backend import (
    BACKEND_PREFERENCE_ORDER,
    CPU_BACKEND,
    BackendCandidate,
    DeviceInfo,
)
from .device_probe import parse_device_list

__all__ = [
    "InferenceProfile",
    "select_profile",
    "MIN_FIT_TARGET_MIB",
    "MAX_FIT_TARGET_MIB",
    "MIN_GPU_SPEEDUP",
    "REJECTED_NOT_FASTER",
]


#: Lower bound of the memory-fit target (MiB).
MIN_FIT_TARGET_MIB = 192
#: Upper bound of the memory-fit target (MiB).
MAX_FIT_TARGET_MIB = 512
#: Fraction used to calculate the free-memory margin (not a consumption cap).
FIT_MEMORY_FRACTION = 0.35
#: A GPU candidate is only selected when it is at least this much faster
#: than the CPU baseline. Below the threshold the GPU is an optimisation
#: that costs time instead of saving it.
MIN_GPU_SPEEDUP = 1.10
#: Rejection reason used when the measured GPU is not faster than the CPU.
REJECTED_NOT_FASTER = "not faster than the cpu baseline"


_REJECTED_PROBE_FAILED = "probe failed"
_REJECTED_NO_DEVICE = "no device reported"
_REJECTED_SOFTWARE_ONLY = "software device only"
_REJECTED_NOT_PREFERRED = "backend not preferred"
_REJECTED_INTEGRATED = "integrated device not allowed"


@dataclass(frozen=True)
class InferenceProfile:
    """The decided inference runtime profile.

    Attributes:
        backend: ``"cuda"``, ``"vulkan"`` or ``"cpu"``.
        device: the selected device name, or None for CPU-only execution.
        fit_target_mib: value for ``--fit-target``.
        reason: human-readable reason for the selection.
        rejected: one dict (``{"backend", "reason"}``) per rejected
            candidate, in evaluation order.
        integrated: True when the selected device is integrated graphics.
    """

    backend: str
    device: str | None
    fit_target_mib: int
    reason: str
    rejected: tuple[dict, ...] = field(default_factory=tuple)
    integrated: bool = False


def _fit_target_mib(device: DeviceInfo, default_fit_target_mib: int) -> int:
    if device.memory_bytes is None:
        return default_fit_target_mib
    reported_free_mib = device.memory_bytes / (1024 * 1024)
    return min(
        MAX_FIT_TARGET_MIB,
        max(MIN_FIT_TARGET_MIB, round(reported_free_mib * FIT_MEMORY_FRACTION)),
    )


def _measured_speedup(
    backend: str, measured: Mapping[str, float],
) -> float | None:
    """Return the measured speed-up of ``backend`` over the CPU baseline.

    The ratio is ``cpu_median / backend_median``: a value above 1 means
    the backend is faster. ``None`` when the comparison is not possible
    (no measurement for the backend, or for the CPU baseline).
    """

    backend_median = measured.get(backend)
    cpu_median = measured.get(CPU_BACKEND)
    if not backend_median or not cpu_median:
        return None
    if backend_median <= 0:
        return None
    return float(cpu_median) / float(backend_median)


def _evaluate(
    candidate: BackendCandidate,
    prefer: tuple[str, ...],
    allow_integrated: bool,
    default_fit_target_mib: int,
):
    """Return ``("selected", profile_fields)`` or ``("rejected", reason)``.

    Rejection checks run in the order fixed by the policy contract. The
    CPU baseline skips the device checks: it is valid with no devices.
    """

    if not candidate.ok:
        return ("rejected", _REJECTED_PROBE_FAILED)

    if candidate.backend == CPU_BACKEND:
        if candidate.backend not in prefer:
            return ("rejected", _REJECTED_NOT_PREFERRED)
        return (
            "selected",
            {
                "backend": CPU_BACKEND,
                "device": None,
                "fit_target_mib": default_fit_target_mib,
                "reason": "cpu baseline",
                "integrated": False,
            },
        )

    devices = [
        device
        for device in parse_device_list(candidate.output)
        if device.backend == candidate.backend
    ]
    if not devices:
        return ("rejected", _REJECTED_NO_DEVICE)
    usable = [device for device in devices if not device.is_software]
    if not usable:
        return ("rejected", _REJECTED_SOFTWARE_ONLY)
    if candidate.backend not in prefer:
        return ("rejected", _REJECTED_NOT_PREFERRED)
    if not allow_integrated:
        usable = [device for device in usable if not device.is_integrated]
        if not usable:
            return ("rejected", _REJECTED_INTEGRATED)

    with_memory = [device for device in usable if device.memory_bytes is not None]
    selected = with_memory[0] if with_memory else usable[0]
    return (
        "selected",
        {
            "backend": candidate.backend,
            "device": selected.name,
            "fit_target_mib": _fit_target_mib(selected, default_fit_target_mib),
            "reason": f"validated {candidate.backend} device {selected.name}",
            "integrated": selected.is_integrated,
        },
    )


def select_profile(
    candidates,
    *,
    prefer=BACKEND_PREFERENCE_ORDER,
    allow_integrated: bool = True,
    default_fit_target_mib: int = 192,
    measurements: Mapping[str, float] | None = None,
    min_gpu_speedup: float = MIN_GPU_SPEEDUP,
) -> InferenceProfile:
    """Select the inference profile from probe candidates.

    Candidates are evaluated in ``prefer`` order (candidates whose backend
    is not preferred are evaluated last). Every candidate that fails a
    policy check is recorded in ``rejected`` with its reason. The first
    candidate that passes every check wins. When no candidate passes, the
    always-valid CPU baseline is returned as the final fallback -- the
    result is never an error.

    ``measurements`` maps a backend to its measured MEDIAN request
    latency in milliseconds. When both the CPU baseline and a GPU
    candidate were measured, the GPU is only selected when it is at
    least ``min_gpu_speedup`` times faster than the CPU baseline. A GPU
    that works but is slower is an optimisation that costs time, so the
    CPU baseline is kept and the candidate is rejected with
    :data:`REJECTED_NOT_FASTER`.
    """

    prefer = tuple(prefer)
    order = {backend: index for index, backend in enumerate(prefer)}
    evaluated = sorted(
        enumerate(candidates),
        key=lambda pair: (
            order.get(pair[1].backend, len(order)),
            pair[0],
        ),
    )

    measured = dict(measurements or {})
    rejected: list[dict] = []
    chosen: dict | None = None
    for _, candidate in evaluated:
        outcome, payload = _evaluate(
            candidate, prefer, allow_integrated, default_fit_target_mib
        )
        if outcome == "rejected":
            rejected.append({"backend": candidate.backend, "reason": payload})
            continue
        if payload["backend"] != CPU_BACKEND:
            speedup = _measured_speedup(payload["backend"], measured)
            if speedup is not None and speedup < min_gpu_speedup:
                rejected.append({
                    "backend": candidate.backend,
                    "reason": (
                        f"{REJECTED_NOT_FASTER} "
                        f"(speedup {speedup:.2f} < {min_gpu_speedup:.2f})"
                    ),
                })
                continue
        if chosen is None:
            chosen = payload

    if chosen is None:
        chosen = {
            "backend": CPU_BACKEND,
            "device": None,
            "fit_target_mib": default_fit_target_mib,
            "reason": "no candidate validated; cpu baseline is the fallback",
            "integrated": False,
        }

    return InferenceProfile(
        backend=chosen["backend"],
        device=chosen["device"],
        fit_target_mib=chosen["fit_target_mib"],
        reason=chosen["reason"],
        rejected=tuple(rejected),
        integrated=chosen["integrated"],
    )
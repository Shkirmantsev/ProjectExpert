"""Backend value types for the portable inference runtime policy.

This module is the single vocabulary used by the device probe, the
selection policy, the launch-plan builder and the deployment launchers.

Design constraints (see the ``portable-inference-runtime`` spec):

* the CPU backend is always available and is the final fallback;
* backends are preferred in the fixed order CUDA -> Vulkan -> CPU;
* a GPU is an optimisation, never a startup prerequisite.

The module is pure data: no I/O, no subprocesses, no platform calls.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CPU_BACKEND",
    "CUDA_BACKEND",
    "VULKAN_BACKEND",
    "BACKEND_PREFERENCE_ORDER",
    "DeviceInfo",
    "BackendCandidate",
]


#: CPU-only execution. Always valid and always the final fallback.
CPU_BACKEND = "cpu"
#: NVIDIA CUDA execution.
CUDA_BACKEND = "cuda"
#: Cross-vendor Vulkan execution (never a software rasteriser).
VULKAN_BACKEND = "vulkan"

#: Candidate order used when no other preference is supplied.
BACKEND_PREFERENCE_ORDER = (CUDA_BACKEND, VULKAN_BACKEND, CPU_BACKEND)


@dataclass(frozen=True)
class DeviceInfo:
    """One device reported by ``llama-server --list-devices``.

    Attributes:
        name: device name as reported, e.g. ``"CUDA0"``, ``"Vulkan1"``,
            or ``"none"`` when the runtime reports no devices.
        description: the raw description text of the report line.
        backend: derived from the name prefix -- ``"cuda"``, ``"vulkan"``,
            ``"metal"`` or ``"cpu"`` for anything else.
        is_software: True for software rasterisers (lavapipe, SwiftShader,
            llvmpipe, softpipe, ...); such devices are never selected.
        is_integrated: True when the description reports an
            ``INTEGRATED_GPU`` device type.
        memory_bytes: reported free memory in bytes, or None when the
            runtime does not report a memory reading. Never invented.
    """

    name: str
    description: str
    backend: str
    is_software: bool = False
    is_integrated: bool = False
    memory_bytes: int | None = None


@dataclass(frozen=True)
class BackendCandidate:
    """The raw outcome of probing one backend runtime.

    Attributes:
        backend: the backend this probe was recorded for
            (``"cuda"``, ``"vulkan"`` or ``"cpu"``).
        ok: True when the probe process itself succeeded.
        exit_code: the probe exit code; ``-1`` for a timeout or a
            transport failure.
        output: raw stdout+stderr of the probe.
        error: transport failure description (timeout, missing binary),
            or None for a completed probe.
    """

    backend: str
    ok: bool
    exit_code: int
    output: str
    error: str | None = None
"""Parse and run ``llama-server --list-devices`` probes.

The probe output format observed on llama.cpp b11515 is::

    Available devices:
      CUDA0: NVIDIA GeForce RTX 4090, CUDA driver version 12.4, ...
      Vulkan0: AMD Radeon RX 7900 (RADV NAVI31), device type: DISCRETE_GPU, ...
      (none)

Parsing rules (spec ``portable-inference-runtime``):

* a line ``"  <name>: <description>"`` is a device;
* the literal name ``(none)`` means NO devices -- an empty list;
* the backend comes from the name prefix: ``CUDA*`` -> ``cuda``,
  ``Vulkan*`` -> ``vulkan``, ``Metal*`` -> ``metal``, anything else -> ``cpu``;
* ``is_software`` is True when a software marker appears in the name or
  description (case-insensitive);
* ``is_integrated`` is True when the description contains
  ``INTEGRATED_GPU`` (case-insensitive);
* ``memory_bytes`` is parsed from a ``"free memory: N MiB"`` fragment when
  present, otherwise from an ``"N MiB"`` fragment; None when absent. Never
  invented;
* unparseable lines are ignored, never fatal.

``probe_binary`` runs the probe as a bounded subprocess and never raises:
a timeout or launch failure is reported through ``BackendCandidate``.
"""

from __future__ import annotations

import os
import re
import subprocess

from .backend import CPU_BACKEND, BackendCandidate, DeviceInfo

__all__ = [
    "SOFTWARE_MARKERS",
    "parse_device_list",
    "probe_binary",
]


#: Description fragments that identify a software rasteriser. Such a
#: device is never selected for inference: it is slower than the validated
#: CPU profile and hides the real hardware state.
SOFTWARE_MARKERS = (
    "lavapipe",
    "swiftshader",
    "llvmpipe",
    "softpipe",
    "microsoft basic render",
    "software rasterizer",
)

# ``  CUDA0: NVIDIA GeForce RTX 4090, ...`` -- an indented name/description.
_DEVICE_LINE = re.compile(r"^\s+([A-Za-z0-9][A-Za-z0-9_.-]*)\s*:\s*(\S.*)$")
# ``  (none)`` or ``  (none):`` -- the runtime reports no devices at all.
_NO_DEVICES_LINE = re.compile(r"^\s*\(none\)\s*:?\s*$")
# The FREE device memory. llama.cpp reports a Vulkan device as
# ``(32334 MiB, 30768 MiB free)``; other backends may use
# ``free memory: 20000 MiB``. A bare ``<N> MiB`` fragment is the TOTAL
# memory, not the free memory, and MUST NOT be used as the free figure:
# the memory-fit budget would then be computed from memory the runtime
# cannot actually use.
_FREE_MEMORY = re.compile(r"free memory:\s*([0-9]+(?:\.[0-9]+)?)\s*MiB", re.IGNORECASE)
_FREE_MEMORY_TRAILING = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*MiB\s+free", re.IGNORECASE)


def _backend_for_name(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith("cuda"):
        return "cuda"
    if lowered.startswith("vulkan"):
        return "vulkan"
    if lowered.startswith("metal"):
        return "metal"
    return "cpu"


def _memory_bytes(description: str) -> int | None:
    """Return the FREE device memory in bytes, or ``None`` when unknown.

    Only an explicitly free figure is accepted. The total memory is never
    substituted for the free memory: the fit budget would then be computed
    from memory the runtime cannot use, which is exactly the failure the
    low-VRAM tolerance exists to prevent.
    """

    match = _FREE_MEMORY.search(description) or _FREE_MEMORY_TRAILING.search(description)
    if match is None:
        return None
    try:
        return int(round(float(match.group(1)) * 1024 * 1024))
    except ValueError:  # pragma: no cover - regex guarantees a number
        return None


def parse_device_list(output: str) -> list[DeviceInfo]:
    """Parse ``llama-server --list-devices`` output into device records.

    Unparseable lines are ignored; the function never raises for input.
    The literal ``(none)`` marker means there are no devices at all and
    yields an empty list.
    """

    devices: list[DeviceInfo] = []
    for line in (output or "").splitlines():
        if _NO_DEVICES_LINE.match(line):
            return []
        match = _DEVICE_LINE.match(line)
        if match is None:
            continue
        name, description = match.group(1), match.group(2).strip()
        haystack = f"{name} {description}".lower()
        is_software = any(marker in haystack for marker in SOFTWARE_MARKERS)
        is_integrated = "integrated_gpu" in description.lower()
        devices.append(
            DeviceInfo(
                name=name,
                description=description,
                backend=_backend_for_name(name),
                is_software=is_software,
                is_integrated=is_integrated,
                memory_bytes=_memory_bytes(description),
            )
        )
    return devices


def _decode(stream) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode("utf-8", errors="replace")
    return str(stream)


def probe_binary(
    binary, *, timeout: float = 15.0, extra_args=("--list-devices",)
) -> BackendCandidate:
    """Run ``binary <extra_args>`` with a bounded timeout and capture output.

    The probe runs with ``shell=False`` and a hard timeout. A timeout or a
    non-zero exit is reported as ``ok=False`` with the exit code (``-1`` for
    a timeout or a launch failure). This function never raises.

    The recorded ``backend`` is derived from the first device the runtime
    reports (``cpu`` when it reports none), so a raw probe result is always
    labelled consistently with its own evidence.
    """

    argv = [os.fspath(binary), *(str(argument) for argument in extra_args)]
    try:
        completed = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            timeout=timeout,
            text=True,
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        output = _decode(exc.stdout) + _decode(exc.stderr)
        devices = parse_device_list(output)
        return BackendCandidate(
            backend=devices[0].backend if devices else CPU_BACKEND,
            ok=False,
            exit_code=-1,
            output=output,
            error=f"probe timed out after {timeout} seconds",
        )
    except OSError as exc:
        return BackendCandidate(
            backend=CPU_BACKEND,
            ok=False,
            exit_code=-1,
            output="",
            error=f"probe could not start: {exc}",
        )
    output = (completed.stdout or "") + (completed.stderr or "")
    devices = parse_device_list(output)
    return BackendCandidate(
        backend=devices[0].backend if devices else CPU_BACKEND,
        ok=completed.returncode == 0,
        exit_code=completed.returncode,
        output=output,
        error=None,
    )
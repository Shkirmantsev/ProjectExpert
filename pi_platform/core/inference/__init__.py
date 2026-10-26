"""Portable inference runtime policy.

One Python-owned place for backend discovery, device selection, the launch
plan and the degradation behaviour. The Bash and PowerShell deployment
launchers collect probe evidence and apply the decision produced here; the
GPU is an optimisation, never a startup prerequisite.

Modules:

* ``backend`` -- backend vocabulary and probe result value types;
* ``device_probe`` -- parse and run ``--list-devices`` probes;
* ``profile`` -- the selection policy (pure, no I/O);
* ``launch`` -- the explicit runtime argument vector and Compose fragments.
"""

from __future__ import annotations

from .backend import (
    BACKEND_PREFERENCE_ORDER,
    CPU_BACKEND,
    CUDA_BACKEND,
    VULKAN_BACKEND,
    BackendCandidate,
    DeviceInfo,
)
from .device_probe import SOFTWARE_MARKERS, parse_device_list, probe_binary
from .launch import build_server_argv, compose_device_fragment
from .profile import InferenceProfile, select_profile

__all__ = [
    "BACKEND_PREFERENCE_ORDER",
    "CPU_BACKEND",
    "CUDA_BACKEND",
    "VULKAN_BACKEND",
    "BackendCandidate",
    "DeviceInfo",
    "SOFTWARE_MARKERS",
    "parse_device_list",
    "probe_binary",
    "InferenceProfile",
    "select_profile",
    "build_server_argv",
    "compose_device_fragment",
]
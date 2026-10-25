"""Build the explicit ``llama-server`` argument vector and Compose fragments.

The runtime flags are emitted as an explicit argument vector. Environment
variables are NOT used for inference flags: llama.cpp's ``LLAMA_ARG_*``
names differ from the flag names (``--batch-size`` is ``LLAMA_ARG_BATCH``,
``--ubatch-size`` is ``LLAMA_ARG_UBATCH``, ``--parallel`` is
``LLAMA_ARG_N_PARALLEL``) and a wrong name is silently ignored.

The multimodal projector always stays on the CPU (``--no-mmproj-offload``,
exactly once): it is ~555 MB of Q8 weights plus runtime buffers and does
not fit a small UMA allocation safely.
"""

from __future__ import annotations

from .backend import CPU_BACKEND, CUDA_BACKEND
from .profile import InferenceProfile

__all__ = [
    "build_server_argv",
    "compose_device_fragment",
]

# Fallback device names used when a GPU backend is requested without an
# explicitly probed device (the documented ``PI_GPU_DEVICE`` defaults).
_DEFAULT_GPU_DEVICE = {CUDA_BACKEND: "CUDA0"}


def build_server_argv(
    *,
    model_path,
    projector_path,
    alias,
    device=None,
    backend: str = CPU_BACKEND,
    fit_target_mib: int = 192,
    ctx_size: int = 2048,
    batch_size: int = 1024,
    ubatch_size: int = 1024,
    parallel: int = 1,
    host: str = "127.0.0.1",
    port: int = 8769,
    api_key_file: str = "llama-api-key",
) -> list[str]:
    """Build the explicit ``llama-server`` argument vector.

    The vector contains, in order: ``--embeddings``, ``--model``,
    ``--mmproj``, ``--alias``, ``--pooling mean``, ``--embd-normalize 2``,
    ``--ctx-size``, ``--batch-size``, ``--ubatch-size``, ``--parallel``,
    ``--host``, ``--port``, ``--api-key-file``.

    For a GPU backend it then carries ``--device <device> --fit on
    --fit-target <mib>``; for the CPU backend ``--device none``. The vector
    always ends with ``--no-mmproj-offload`` exactly once.
    """

    argv = [
        "--embeddings",
        "--model",
        str(model_path),
        "--mmproj",
        str(projector_path),
        "--alias",
        str(alias),
        "--pooling",
        "mean",
        "--embd-normalize",
        "2",
        "--ctx-size",
        str(ctx_size),
        "--batch-size",
        str(batch_size),
        "--ubatch-size",
        str(ubatch_size),
        "--parallel",
        str(parallel),
        "--host",
        str(host),
        "--port",
        str(port),
        "--api-key-file",
        str(api_key_file),
    ]
    if backend == CPU_BACKEND:
        argv += ["--device", "none"]
    else:
        device_name = str(device) if device else _DEFAULT_GPU_DEVICE.get(backend, "Vulkan0")
        argv += ["--device", device_name, "--fit", "on", "--fit-target", str(fit_target_mib)]
    argv.append("--no-mmproj-offload")
    return argv


def compose_device_fragment(profile: InferenceProfile) -> dict[str, str]:
    """Return the Compose environment fragment for a profile.

    ``PI_ACCELERATOR`` names the selected backend, ``PI_GPU_DEVICE`` the
    selected device (always ``"none"`` for the CPU backend) and
    ``PI_FIT_TARGET`` the computed fit target in MiB.
    """

    device = "none"
    if profile.backend != CPU_BACKEND and profile.device:
        device = profile.device
    return {
        "PI_ACCELERATOR": profile.backend,
        "PI_GPU_DEVICE": device,
        "PI_FIT_TARGET": str(profile.fit_target_mib),
    }
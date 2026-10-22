"""Portable accelerator selection before loading model weights."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceSelection:
    device: str
    reason: str


def select_device(device: str = "auto", *, min_free_bytes: int = 3 * 1024**3) -> DeviceSelection:
    requested = (device or "auto").strip().lower()
    if requested not in {"auto", "cpu", "cuda", "mps"}:
        raise ValueError(f"unknown device {device!r}; expected auto, cpu, cuda or mps")
    if requested != "auto":
        return DeviceSelection(requested, "explicit selection")
    try:
        import torch
        if torch.cuda.is_available():
            free, _ = torch.cuda.mem_get_info()
            if free >= min_free_bytes:
                return DeviceSelection("cuda", "CUDA available with safe free memory")
            return DeviceSelection("cpu", "available GPU memory below safe threshold")
    except Exception:
        return DeviceSelection("cpu", "accelerator availability or free memory could not be verified")
    # MPS has no portable free-device-memory query. CPU remains the safe
    # automatic choice; an operator can still explicitly select MPS.
    return DeviceSelection("cpu", "no accelerator with verified safe free memory")

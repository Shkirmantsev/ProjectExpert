from __future__ import annotations

from dataclasses import dataclass
import os


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


@dataclass(frozen=True)
class Settings:
    api_base: str
    api_key: str
    tail_host: str
    tail_ip: str
    port: int
    token: str
    log_level: str
    allowed_project_roots: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        token = required("HERMES_SIDECAR_TOKEN")
        if len(token) < 32:
            raise RuntimeError("HERMES_SIDECAR_TOKEN must be >= 32 characters")
        base = required("HERMES_API_BASE_URL").rstrip("/")
        if base.endswith("/v1"):
            raise RuntimeError("HERMES_API_BASE_URL must be the server root, e.g. http://127.0.0.1:8642 (without /v1)")
        port = int(os.getenv("SIDECAR_PORT", "8775"))
        if not 1 <= port <= 65535:
            raise RuntimeError("SIDECAR_PORT must be in 1..65535")
        allowed_roots = tuple(
            item.strip()
            for item in required("HERMES_ALLOWED_PROJECT_ROOTS").split(os.pathsep)
            if item.strip()
        )
        if not allowed_roots:
            raise RuntimeError("HERMES_ALLOWED_PROJECT_ROOTS must contain at least one root")
        return cls(
            api_base=base,
            api_key=required("HERMES_API_KEY"),
            tail_host=required("SIDECAR_TAILSCALE_HOST"),
            tail_ip=required("SIDECAR_TAILSCALE_IP"),
            port=port,
            token=token,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            allowed_project_roots=allowed_roots,
        )

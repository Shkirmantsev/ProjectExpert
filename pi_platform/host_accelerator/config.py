"""Accelerator runtime configuration (G1)."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field


__all__ = ["AcceleratorConfig", "BindAddressError", "DEFAULT_CONFIG"]


class BindAddressError(ValueError):
    """Raised when the configured bind address is rejected."""


# Defaults: the accelerator is local-only by default and
# runs on port 8791 (an unprivileged port above 1024).
DEFAULT_BIND_ADDRESS = "127.0.0.1"
DEFAULT_PORT = 8791
DEFAULT_MAX_REQUEST_BYTES = 1 * 1024 * 1024          # 1 MiB
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_CONCURRENT_REQUESTS = 4
DEFAULT_TOKEN_PATH = os.path.join(
    ".project-intelligence-cache", "accelerator", "token",
)
DEFAULT_AUDIT_LOG_PATH = os.path.join(
    ".project-intelligence-cache", "accelerator", "audit.jsonl",
)
DEFAULT_ALLOW_LIST_PATH = os.path.join(
    ".project-intelligence-cache", "accelerator", "allow_list.json",
)
DEFAULT_ALLOW_WIDE_BIND = False
DEFAULT_BIND_HOST_ENV = "ACCELERATOR_BIND_HOST"
DEFAULT_BIND_PORT_ENV = "ACCELERATOR_BIND_PORT"
DEFAULT_TOKEN_PATH_ENV = "ACCELERATOR_TOKEN_PATH"
DEFAULT_AUDIT_LOG_PATH_ENV = "ACCELERATOR_AUDIT_LOG_PATH"
DEFAULT_ALLOW_LIST_PATH_ENV = "ACCELERATOR_ALLOW_LIST_PATH"
DEFAULT_ALLOW_WIDE_BIND_ENV = "ACCELERATOR_ALLOW_WIDE_BIND"


@dataclass(frozen=True)
class AcceleratorConfig:
    """Runtime configuration for the host accelerator.

    The bind address is validated at construction time:
    loopback is always allowed; private + wide bind only when
    ``allow_wide_bind=True``; public addresses are rejected
    unconditionally.
    """

    bind_address: str = DEFAULT_BIND_ADDRESS
    port: int = DEFAULT_PORT
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    max_concurrent_requests: int = DEFAULT_MAX_CONCURRENT_REQUESTS
    token_path: str = DEFAULT_TOKEN_PATH
    audit_log_path: str = DEFAULT_AUDIT_LOG_PATH
    allow_list_path: str = DEFAULT_ALLOW_LIST_PATH
    allow_wide_bind: bool = DEFAULT_ALLOW_WIDE_BIND

    def __post_init__(self) -> None:
        if not self.bind_address:
            raise BindAddressError("bind_address is required")
        try:
            addr = ipaddress.ip_address(self.bind_address)
        except ValueError as exc:
            raise BindAddressError(
                f"bind_address is not a valid IP: {self.bind_address!r}"
            ) from exc
        if not (addr.is_loopback or addr.is_private):
            raise BindAddressError(
                f"bind_address {self.bind_address!r} is neither loopback "
                f"nor private; refused for security reasons"
            )
        if not addr.is_loopback and not self.allow_wide_bind:
            raise BindAddressError(
                f"bind_address {self.bind_address!r} is private but "
                f"allow_wide_bind is False; set "
                f"{DEFAULT_ALLOW_WIDE_BIND_ENV}=1 to enable"
            )
        if self.port < 1 or self.port > 65535:
            raise BindAddressError(
                f"port must be in [1, 65535], got {self.port}"
            )
        if self.max_request_bytes <= 0:
            raise BindAddressError("max_request_bytes must be positive")
        if self.request_timeout_seconds <= 0:
            raise BindAddressError(
                "request_timeout_seconds must be positive"
            )
        if self.max_concurrent_requests <= 0:
            raise BindAddressError(
                "max_concurrent_requests must be positive"
            )

    @classmethod
    def from_env(
        cls, env: dict | None = None,
    ) -> "AcceleratorConfig":
        """Build a config from environment variables.

        Operators who want to run the accelerator in CI or
        test environments override the bind address / token
        path via env vars; the constructor's validation still
        applies.
        """
        e = env if env is not None else os.environ
        bind_address = e.get(DEFAULT_BIND_HOST_ENV, DEFAULT_BIND_ADDRESS)
        try:
            port = int(e.get(DEFAULT_BIND_PORT_ENV, str(DEFAULT_PORT)))
        except ValueError as exc:
            raise BindAddressError(
                f"{DEFAULT_BIND_PORT_ENV} is not an integer"
            ) from exc
        return cls(
            bind_address=bind_address,
            port=port,
            token_path=e.get(DEFAULT_TOKEN_PATH_ENV, DEFAULT_TOKEN_PATH),
            audit_log_path=e.get(
                DEFAULT_AUDIT_LOG_PATH_ENV, DEFAULT_AUDIT_LOG_PATH,
            ),
            allow_list_path=e.get(
                DEFAULT_ALLOW_LIST_PATH_ENV, DEFAULT_ALLOW_LIST_PATH,
            ),
            allow_wide_bind=e.get(
                DEFAULT_ALLOW_WIDE_BIND_ENV, "0",
            ) not in ("", "0", "false", "False"),
        )

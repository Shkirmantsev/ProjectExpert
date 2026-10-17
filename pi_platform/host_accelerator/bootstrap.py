"""Bootstrap helpers for the host accelerator (G3)."""

from __future__ import annotations

import os

from pi_platform.ports.retrieval.embedding_profile import (
    EmbeddingProfileRegistry,
)

from .audit import AuditLog
from .config import AcceleratorConfig
from .security import ModelAllowList, TokenStore


__all__ = [
    "bootstrap_token",
    "ensure_audit_log",
    "ensure_allow_list_file",
    "bootstrap_all",
]


def bootstrap_token(config: AcceleratorConfig) -> str:
    """Return the existing token or create a new one.

    Idempotent: if the token file already exists, it is read
    and returned without modification. Otherwise a fresh
    32-byte URL-safe token is generated, persisted with
    mode 0o600, and returned.
    """
    store = TokenStore(config.token_path)
    if store.exists():
        return store.read()
    return store.rotate()


def ensure_audit_log(config: AcceleratorConfig) -> AuditLog:
    """Create the audit log directory and return an
    :class:`AuditLog` bound to ``config.audit_log_path``."""
    log = AuditLog(config.audit_log_path)
    directory = os.path.dirname(config.audit_log_path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
        try:
            os.chmod(directory, 0o700)
        except (OSError, AttributeError):
            pass
    return log


def ensure_allow_list_file(
    config: AcceleratorConfig,
    *,
    registry: EmbeddingProfileRegistry | None = None,
) -> ModelAllowList:
    """Ensure the allow-list file exists and contains the
    three built-in profiles. Returns the live
    :class:`ModelAllowList`."""
    allow_list = ModelAllowList(config.allow_list_path)
    allow_list.ensure_default_registrations(registry=registry)
    return allow_list


def bootstrap_all(
    config: AcceleratorConfig,
    *,
    registry: EmbeddingProfileRegistry | None = None,
) -> tuple[str, AuditLog, ModelAllowList]:
    """Idempotent bootstrap for the accelerator: token +
    audit log + allow-list. Returns ``(token, audit_log,
    allow_list)``."""
    token = bootstrap_token(config)
    audit = ensure_audit_log(config)
    allow_list = ensure_allow_list_file(config, registry=registry)
    return token, audit, allow_list

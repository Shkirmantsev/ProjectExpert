"""Phase 7 §59.10 secret backend adapters.

The adapter layer ships the documented backends the
default Secret Provider composes:

* :class:`EnvironmentBackend` — resolves ``env://``
  references through ``os.environ``.
* :class:`EncryptedLocalStoreBackend` — resolves
  ``secret://local/<name>`` references through an
  encrypted local store (deterministic test double;
  production deployment MUST replace this stub with a
  real Fernet / AES-GCM wrapper through the Phase 1
  ``LicenseGate``).
* :class:`KeychainBackend` — resolves
  ``secret://enterprise/<name>`` references through an
  OS keychain (deterministic test double; production
  deployment MUST replace this stub with a real
  ``keyring`` adapter through the Phase 1
  ``LicenseGate``).

The default provider MUST compose at least the
:class:`EnvironmentBackend`; the other backends are
opt-in.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional

from pi_platform.ports.control.secrets import SecretReference


__all__ = [
    "EncryptedLocalStoreBackend",
    "EnvironmentBackend",
    "KeychainBackend",
]


@dataclass
class EnvironmentBackend:
    """Backend that resolves ``env://<name>`` references
    through ``os.environ``.
    """

    def __call__(self, reference: SecretReference) -> Optional[str]:
        if reference.scheme != "env":
            return None
        return os.environ.get(reference.name)


@dataclass
class EncryptedLocalStoreBackend:
    """Backend that resolves ``secret://local/<name>``
    references through an encrypted local store.

    The default implementation is a deterministic test
    double keyed by the reference name. Production
    deployments MUST swap this stub for a real Fernet /
    AES-GCM wrapper through the Phase 1 ``LicenseGate``
    after the wrapper's SPDX entry has been confirmed.
    """

    _store: Mapping[str, str] = field(default_factory=dict)

    def __call__(self, reference: SecretReference) -> Optional[str]:
        if reference.scheme != "secret":
            return None
        if reference.backend != "local":
            return None
        return self._store.get(reference.name)

    def register(self, name: str, value: str) -> None:
        """Test seam: register a value for ``name`` in the
        encrypted local store. Production wrappers MUST
        encrypt the value at rest.
        """
        self._store = {**self._store, name: value}


@dataclass
class KeychainBackend:
    """Backend that resolves ``secret://enterprise/<name>``
    references through an OS keychain.

    The default implementation is a deterministic test
    double. Production deployments MUST swap this stub
    for a real ``keyring`` adapter through the Phase 1
    ``LicenseGate``.
    """

    _store: Mapping[str, str] = field(default_factory=dict)

    def __call__(self, reference: SecretReference) -> Optional[str]:
        if reference.scheme != "secret":
            return None
        if reference.backend != "enterprise":
            return None
        return self._store.get(reference.name)

    def register(self, name: str, value: str) -> None:
        """Test seam: register a value for ``name`` in the
        keychain. Production wrappers MUST persist the
        value through the OS keychain API.
        """
        self._store = {**self._store, name: value}
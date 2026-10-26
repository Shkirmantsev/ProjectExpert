"""Token store and model allow-list (G3)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from typing import Dict, FrozenSet, Iterable, Optional

from pi_platform.ports.retrieval.embedding_profile import (
    EMBEDDINGGEMMA2_512,
    HASHING_DEFAULT,
    EMBEDDINGGEMMA2_GGUF_512,
    EmbeddingProfile,
    EmbeddingProfileRegistry,
)


__all__ = [
    "TokenStore",
    "TokenError",
    "ModelAllowList",
    "AllowListError",
]


class TokenError(RuntimeError):
    """Raised when the token store cannot satisfy a request."""


class TokenStore:
    """Ephemeral bearer token store.

    The token is stored at ``config.token_path`` (default
    ``.project-intelligence-cache/accelerator/token``), which
    is OUTSIDE Git. The file is created with mode 0o600 (read/
    write for the owner only) on POSIX systems; the test is
    best-effort on Windows.

    The token is generated with ``secrets.token_urlsafe(32)``
    which yields a 32-byte (256-bit) URL-safe random token.
    """

    def __init__(self, token_path: str) -> None:
        self._path = token_path

    @property
    def path(self) -> str:
        return self._path

    def read(self) -> str:
        """Read the token from disk.

        Raises :class:`TokenError` if the token file does not
        exist or is unreadable. The token is trimmed of
        trailing whitespace; an empty file is treated as
        missing.
        """
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                token = f.read().strip()
        except FileNotFoundError as exc:
            raise TokenError(
                f"token file {self._path!r} does not exist; run "
                f"`bootstrap_token` first"
            ) from exc
        except OSError as exc:
            raise TokenError(
                f"failed to read token file {self._path!r}: {exc}"
            ) from exc
        if not token:
            raise TokenError(
                f"token file {self._path!r} is empty"
            )
        return token

    def write(self, token: str) -> None:
        """Write the token to disk with mode 0o600.

        The parent directory is created with mode 0o700 on
        POSIX systems. On Windows the mode is a best-effort;
        Windows ACL is the operator's responsibility.
        """
        if not token:
            raise TokenError("token is empty; refusing to write")
        self._ensure_directory()
        with open(self._path, "w", encoding="utf-8") as f:
            f.write(token)
        self._chmod_600(self._path)
        self._chmod_700(os.path.dirname(self._path))

    def rotate(self) -> str:
        """Generate a new token, persist it, return the new value.

        This invalidates the previously issued token
        immediately; operators must distribute the new token
        to all clients.
        """
        new_token = secrets.token_urlsafe(32)
        self.write(new_token)
        return new_token

    def delete(self) -> None:
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass

    def exists(self) -> bool:
        return os.path.isfile(self._path)

    def constant_time_compare(self, provided: str, expected: str) -> bool:
        """Compare two token strings in constant time."""
        return hmac.compare_digest(
            provided.encode("utf-8"),
            expected.encode("utf-8"),
        )

    # -- internal helpers --------------------------------------------

    def _ensure_directory(self) -> None:
        directory = os.path.dirname(self._path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
            self._chmod_700(directory)

    @staticmethod
    def _chmod_600(path: str) -> None:
        try:
            os.chmod(path, 0o600)
        except (OSError, AttributeError):
            # Windows: best-effort.
            pass

    @staticmethod
    def _chmod_700(path: str) -> None:
        try:
            os.chmod(path, 0o700)
        except (OSError, AttributeError):
            pass


class AllowListError(RuntimeError):
    """Raised when the allow-list cannot satisfy a request."""


# Pre-registered identities: the built-in
# EmbeddingProfile values from the v0.8 refinement.
DEFAULT_ALLOWED_IDENTITIES: FrozenSet[str] = frozenset({
    HASHING_DEFAULT.identity(),
    EMBEDDINGGEMMA2_512.identity(),
    EMBEDDINGGEMMA2_GGUF_512.identity(),
})


class ModelAllowList:
    """Allow-list of ``EmbeddingProfile`` identities.

    The allow-list persists to
    ``.project-intelligence-cache/accelerator/allow_list.json``
    as a JSON object
    ``{"identities": ["<identity1>", "<identity2>", ...]}``.

    Operators register new profiles via ``register(profile)``;
    the new identity is added in memory and persisted to disk.
    """

    def __init__(self, allow_list_path: str) -> None:
        self._path = allow_list_path
        if os.path.isfile(allow_list_path):
            self._identities: FrozenSet[str] = self._load()
        else:
            # Persist the default allow-list on first use so
            # the on-disk file is always present and the
            # default registrations are visible to operators.
            self._identities = DEFAULT_ALLOWED_IDENTITIES
            self._save(self._identities)

    @property
    def path(self) -> str:
        return self._path

    @property
    def identities(self) -> FrozenSet[str]:
        return self._identities

    def is_allowed(
        self, *, embedding_profile: EmbeddingProfile,
    ) -> bool:
        return embedding_profile.identity() in self._identities

    def is_allowed_identity(self, identity: str) -> bool:
        return identity in self._identities

    def register(
        self, embedding_profile: EmbeddingProfile,
        *, persist: bool = True,
    ) -> None:
        new = self._identities | {embedding_profile.identity()}
        object.__setattr__(self, "_identities", new)
        if persist:
            self._save(new)

    def unregister(
        self, embedding_profile: EmbeddingProfile,
        *, persist: bool = True,
    ) -> None:
        new = self._identities - {embedding_profile.identity()}
        object.__setattr__(self, "_identities", new)
        if persist:
            self._save(new)

    def ensure_default_registrations(
        self, registry: Optional[EmbeddingProfileRegistry] = None,
    ) -> int:
        """Register the built-in profiles if they are not
        already in the allow-list. Returns the number of new
        registrations performed."""
        before = self._identities
        for profile in (
            HASHING_DEFAULT, EMBEDDINGGEMMA2_512,
            EMBEDDINGGEMMA2_GGUF_512,
        ):
            if profile.identity() not in before:
                before = before | {profile.identity()}
        added = len(before - self._identities)
        if added > 0:
            object.__setattr__(self, "_identities", before)
            self._save(before)
        return added

    # -- internal helpers --------------------------------------------

    def _load(self) -> FrozenSet[str]:
        if not os.path.isfile(self._path):
            return DEFAULT_ALLOWED_IDENTITIES
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise AllowListError(
                f"failed to read allow-list {self._path!r}: {exc}"
            ) from exc
        identities = payload.get("identities") if isinstance(
            payload, dict,
        ) else None
        if not isinstance(identities, list):
            raise AllowListError(
                f"allow-list {self._path!r} is malformed: missing "
                f"'identities' list"
            )
        return frozenset(str(i) for i in identities)

    def _save(self, identities: FrozenSet[str]) -> None:
        directory = os.path.dirname(self._path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
            try:
                os.chmod(directory, 0o700)
            except (OSError, AttributeError):
                pass
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(
                {"identities": sorted(identities)},
                f, indent=2, sort_keys=True,
            )
        try:
            os.chmod(self._path, 0o600)
        except (OSError, AttributeError):
            pass

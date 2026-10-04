"""Deterministic JSON / YAML serialization for the v0.8 Project Intelligence Platform.

The canonical serializer is the only place that decides how every
canonical artifact is encoded. It guarantees:

* sorted keys (recursive);
* canonical line endings (``\\n``);
* trailing newline at end of file;
* stable identifier-array ordering (sorted ascending by string);
* no embedded volatile data (timestamps, hostnames).

The serializer is intentionally small and side-effect free; it has no
filesystem, Git or license coupling so it can be reused inside the
content-addressing utility, the OKF adapter and the CLI.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping, Optional, Sequence

__all__ = [
    "canonical_dump_json",
    "canonical_dump_yaml",
    "canonical_load_json",
    "canonical_load_yaml",
    "normalize_identifier_list",
    "normalize_optional_str",
    "normalize_str",
    "ID_SORT_KEY",
]


ID_SORT_KEY = re.compile(r"^[A-Za-z0-9_.\-:]+$")


def normalize_str(value: Any) -> str:
    """Normalise a scalar string to its canonical form.

    Non-string scalars are coerced via ``str``. Newlines are normalised
    to ``\\n`` so platform text round-trips across OSes.
    """

    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_optional_str(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return normalize_str(value)


def normalize_identifier_list(values: Iterable[str]) -> tuple[str, ...]:
    """Sort and dedup an identifier array deterministically."""

    cleaned = {normalize_str(v) for v in values if v is not None and v != ""}
    return tuple(sorted(cleaned))


def _stable_default(value: Any) -> Any:
    """Apply deterministic transformations to a value before encoding."""

    if isinstance(value, Mapping):
        return {k: _stable_default(value[k]) for k in sorted(value.keys())}
    if isinstance(value, (list, tuple)):
        return [_stable_default(x) for x in value]
    return value


def canonical_dump_json(value: Any) -> bytes:
    """Encode ``value`` as canonical JSON bytes.

    Sorted keys, ``ensure_ascii=False`` so unicode round-trips,
    ``separators=(",", ":")`` so the output is compact, and a trailing
    newline so the artefact is text-file friendly.
    """

    payload = _stable_default(value)
    text = json.dumps(payload, sort_keys=False, ensure_ascii=False,
                      separators=(",", ":"), default=str)
    return (text + "\n").encode("utf-8")


def canonical_load_json(raw: str | bytes) -> Any:
    """Decode canonical JSON produced by :func:`canonical_dump_json`."""

    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
    return json.loads(text)


# ---------------------------------------------------------------------------
# YAML helpers
#
# PyYAML is part of the optional runtime dependencies; when it is not
# installed, the YAML helpers raise a clear ImportError so callers can
# choose the JSON path instead. The platform avoids depending on YAML at
# import time because some production images ship without it.
# ---------------------------------------------------------------------------


def _yaml():
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError(
            "PyYAML is required for canonical YAML I/O; install it via "
            "`pip install pyyaml` or use the JSON helpers instead."
        ) from exc
    return yaml


def canonical_dump_yaml(value: Any) -> bytes:
    """Encode ``value`` as deterministic YAML bytes with sorted keys.

    ``sort_keys=True`` is sufficient for the YAML representation because
    PyYAML emits block-style mapping literals in key order.
    """

    yaml = _yaml()
    payload = _stable_default(value)
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=True,
                         default_flow_style=False)
    return (text + "\n" if not text.endswith("\n") else text).encode("utf-8")


def canonical_load_yaml(raw: str | bytes) -> Any:
    """Decode canonical YAML produced by :func:`canonical_dump_yaml`."""

    yaml = _yaml()
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
    return yaml.safe_load(text)
"""Phase 10 A2A wire-envelope translation.

The wire format used in v1.0 is the minimum A2A envelope required
by the §50/§51 capability. The shape is a small JSON object:

```json
{
  "taskId": "<id>",
  "sessionId": "<session>",
  "messages": [{"role": "user", "parts": [{"kind": "text", "text": "..."}]}],
  "metadata": {}
}
```

The dict shape is documented and versioned through
``A2A_SPEC_VERSION`` in :mod:`pi_platform.core.a2a`. The translation
functions in this module keep the wire types on this side of the
adapter boundary.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional, Sequence

from pi_platform.ports.a2a import (
    A2aError,
    A2aMessage,
    A2aMessagePart,
    A2aSpecVersion,
    A2aTask,
    A2aTaskResult,
    A2aTaskStatus,
)


WIRE_VERSION_KEY = "wireVersion"


SUPPORTED_WIRE_VERSIONS = ("1.0", "1")


def parse_task_envelope(payload: Mapping[str, Any]) -> A2aTask:
    """Translate a wire payload into the :class:`A2aTask` value type."""
    wire_version = str(payload.get(WIRE_VERSION_KEY, "1"))
    if wire_version not in SUPPORTED_WIRE_VERSIONS:
        raise A2aError(f"unsupported wire version: {wire_version!r}")

    task_id = str(payload.get("taskId") or "")
    if not task_id:
        raise A2aError("missing taskId")

    raw_messages = payload.get("messages") or []
    messages: list[A2aMessage] = []
    for raw in raw_messages:
        if not isinstance(raw, Mapping):
            raise A2aError("invalid message shape")
        messages.append(
            A2aMessage(
                role=str(raw.get("role", "user")),
                parts=tuple(_parse_part(p) for p in (raw.get("parts") or [])),
            )
        )

    return A2aTask(
        task_id=task_id,
        session_id=payload.get("sessionId"),
        messages=tuple(messages),
        metadata=dict(payload.get("metadata") or {}),
    )


def serialise_task_result(result: A2aTaskResult) -> str:
    """Render a :class:`A2aTaskResult` as a wire envelope.

    The output is JSON with sorted keys so the metric diff in the
    quality-gates suites stays deterministic.
    """
    body: dict[str, Any] = {WIRE_VERSION_KEY: "1"}
    body.update(result.as_dict())
    return json.dumps(body, sort_keys=True)


def _parse_part(raw: Mapping[str, Any]) -> A2aMessagePart:
    kind = str(raw.get("kind", "text"))
    if kind == "text":
        return A2aMessagePart(kind="text", text=str(raw.get("text", "")))
    if kind == "data":
        data = raw.get("data") or {}
        if not isinstance(data, Mapping):
            raise A2aError("data part must be an object")
        return A2aMessagePart(kind="data", data=dict(data))
    return A2aMessagePart(kind=kind)

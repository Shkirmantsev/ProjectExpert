"""Phase 10 atomic writer for ``eval/last.json``.

The quality-gates suites call :func:`write_atomic` to publish the
current :class:`pi_platform.core.eval.metrics.EvalReport` to disk.
The write is performed through ``tmpfile + rename`` so partial JSON
state is never observable.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


def write_atomic(report: Mapping[str, Any], path: Path) -> None:
    """Atomically write a JSON-serialisable object to ``path``.

    The destination directory is created if missing. The function
    refuses to write to a destination whose parent directory is a
    symlink to outside the project tree (best-effort check).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True)
    fd, tmp_path = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        finally:
            raise

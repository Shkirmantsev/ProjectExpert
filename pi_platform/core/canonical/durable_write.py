"""Durable atomic canonical bytes, preserving existing ordinary access modes."""
import os
from pathlib import Path
import stat
import tempfile


def sync_parent_directories(path: Path) -> None:
    """Persist new ancestor entries up to the canonical bind/filesystem mount."""
    if os.name != 'posix':
        return
    parent = Path(path).parent
    while True:
        descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if parent.parent == parent or parent.is_mount():
            return
        parent = parent.parent


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) & 0o777 if path.exists() else 0o644
    descriptor, temporary = tempfile.mkstemp(prefix='.canonical-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            if os.name == 'posix':
                os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_parent_directories(path)
    finally:
        Path(temporary).unlink(missing_ok=True)

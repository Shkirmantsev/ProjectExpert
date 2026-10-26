"""One Hugging Face cache layout and conservative interrupted-download cleanup."""
from pathlib import Path
import time


def hub_cache(root):
    """PI_MODEL_CACHE/HF_HOME names the cache home, not the hub subdirectory."""
    return str(Path(root).expanduser() / 'hub') if root else None


def prune_incomplete(root, *, min_age_seconds=86400, now=None):
    """Remove old incomplete HF blobs only while holding the downloader's lock.

    Completed weights, recent partial downloads and active downloads are retained.
    Include the historical flat layout so earlier installations can reclaim it.
    """
    from filelock import FileLock, Timeout
    if min_age_seconds < 0:
        raise ValueError('Minimum age must be nonnegative')
    now = time.time() if now is None else now
    root = Path(root).expanduser().resolve()
    removed, reclaimed, skipped = [], 0, 0
    for cache in (root, root / 'hub'):
        for path in cache.glob('models--*/blobs/*.incomplete'):
            if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink():
                continue
            lock = cache / '.locks' / path.parent.parent.name / (path.name.removesuffix('.incomplete') + '.lock')
            lock.parent.mkdir(parents=True, exist_ok=True)
            try:
                with FileLock(str(lock), timeout=0):
                    if not path.exists():
                        continue
                    stat = path.stat()
                    if now - stat.st_mtime < min_age_seconds:
                        skipped += 1
                        continue
                    path.unlink()
                    removed.append(str(path.relative_to(root)))
                    reclaimed += stat.st_size
            except Timeout:
                skipped += 1
    return {'removed': removed, 'reclaimed_bytes': reclaimed, 'skipped': skipped}

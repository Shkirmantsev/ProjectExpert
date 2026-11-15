"""Confine private runtime storage and exclude it from future Git additions."""
import os
from pathlib import Path
import subprocess


def ensure_private_cache(target, cache_root):
    target, cache_root = Path(target).resolve(), Path(cache_root).absolute()
    if cache_root.is_symlink():
        raise ValueError('Private cache must not contain symlinks')
    cache_root = cache_root.resolve()
    cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == 'posix':
        cache_root.chmod(0o700)
    if not cache_root.is_relative_to(target) or cache_root == target:
        return
    if not (target / '.git').exists():
        return  # Managed mounts use a private runtime volume, without Git metadata.
    relative = cache_root.relative_to(target).as_posix()
    def git(*args):
        return subprocess.run(['git', '-C', str(target), *args], capture_output=True, check=True).stdout
    if git('ls-files', '-z', '--', relative):
        raise ValueError('Runtime cache is tracked by Git; remove it from tracking and review history before processing protected data')
    path = Path(os.fsdecode(git('rev-parse', '--git-path', 'info/exclude')).strip())
    path = path if path.is_absolute() else target / path
    if path.is_symlink():
        raise ValueError('Git exclusion file must not be a symlink')
    existing = path.read_text(encoding='utf-8') if path.exists() else ''
    pattern = '/' + relative + '/'
    if pattern not in existing.splitlines():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as stream:
            stream.write(('' if not existing or existing.endswith('\n') else '\n') + pattern + '\n')

"""Container-private browser bootstrap, reachable by the Docker operator."""

import os
from pathlib import Path
import secrets
import stat
import tempfile


_MANAGED_ADMIN_KEY = Path('/tmp/projectexpert-local-ui/key')


def provision_local_owner_key() -> str:
    directory = _MANAGED_ADMIN_KEY.parent
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or (
        os.name != 'nt' and (info.st_uid != os.geteuid() or info.st_mode & 0o077)
    ):
        raise ValueError('Managed local UI requires a private credential directory')
    key = secrets.token_urlsafe(32)
    with tempfile.NamedTemporaryFile(dir=directory, mode='w', delete=False, encoding='ascii') as stream:
        staged = Path(stream.name)
        stream.write(key)
    try:
        staged.replace(_MANAGED_ADMIN_KEY)
    finally:
        staged.unlink(missing_ok=True)
    return key


def main() -> None:
    """Emit a browser credential only to the invoking Docker exec process."""
    if not os.environ.get('PI_UI_TOKEN') and _MANAGED_ADMIN_KEY.is_file():
        print(_MANAGED_ADMIN_KEY.read_text(encoding='ascii').strip())


if __name__ == '__main__':
    main()

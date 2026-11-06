"""Export the deployment kit without overwriting operator-owned files."""
from pathlib import Path
import argparse
import os
import shutil
import stat
import tempfile

FILES = ('runtime-entrypoint.sh', 'runtime_supervisor.py', 'compose.ui-vulkan.yaml', 'compose.yaml', 'deployment.env', 'Makefile', 'start.sh', 'start.ps1', 'stop.ps1', 'README.md', 'compose.sh', 'compose.ps1', 'compose.accelerator.yaml', 'compose.vulkan.yaml', 'compose.cuda.yaml', 'compose.cpu.yaml', 'compose.windows-gpu.yaml', 'accelerator-lock.json', 'setup-windows-accelerator.ps1', 'url.sh', 'url.ps1', '.gitignore')


def _repair_root_owner(path: Path, owner, *, directory: bool = False) -> None:
    """Repair only exporter-owned entries, never linked external objects."""
    try:
        current = path.lstat()
    except FileNotFoundError:
        return
    eligible = (stat.S_ISDIR(current.st_mode) if directory else
                stat.S_ISREG(current.st_mode) and current.st_nlink == 1)
    if current.st_uid == 0 and eligible:
        os.chown(path, owner.st_uid, owner.st_gid, follow_symlinks=False)


def _repair_kit_ownership(destination: Path) -> None:
    if not (hasattr(os, 'chown') and os.getuid() == 0):
        return
    # Preserve an explicit non-root kit owner. A root-owned/pre-created kit
    # inherits the mounted project owner, not the container's root identity.
    owner = destination.stat()
    if owner.st_uid == 0:
        owner = destination.parent.stat()
    _repair_root_owner(destination, owner, directory=True)
    for name in FILES:
        _repair_root_owner(destination / name, owner)
    backup_root = destination / '.kit-backups'
    if backup_root.is_dir() and not backup_root.is_symlink():
        _repair_root_owner(backup_root, owner, directory=True)
        for backup in backup_root.glob('upgrade-*'):
            if backup.is_dir() and not backup.is_symlink():
                _repair_root_owner(backup, owner, directory=True)
                for name in FILES:
                    _repair_root_owner(backup / name, owner)


def export(source: Path, destination: Path, *, upgrade: bool = False) -> None:
    if destination.is_symlink():
        raise ValueError('Refusing symlinked kit destination')
    if upgrade:
        for name in FILES:
            if name != 'deployment.env' and (destination / name).is_symlink():
                raise ValueError(f'Refusing upgrade of managed symlink: {name}')
        if (destination / '.kit-backups').is_symlink():
            raise ValueError('Refusing symlinked kit backup directory')
    destination.mkdir(parents=True, exist_ok=True)
    _repair_kit_ownership(destination)
    backup = None
    for name in FILES:
        path = destination / name
        content = (source / name).read_bytes()
        if upgrade and name != 'deployment.env' and path.exists():
            if path.read_bytes() == content:
                print(f'Unchanged {name}')
                continue
            if backup is None:
                backup_root = destination / '.kit-backups'
                if backup_root.is_symlink():
                    raise ValueError('Refusing symlinked kit backup directory')
                backup_root.mkdir(exist_ok=True)
                backup = Path(tempfile.mkdtemp(prefix='upgrade-', dir=backup_root))
                if hasattr(os, 'chown') and os.getuid() == 0:
                    owner = destination.stat()
                    os.chown(backup_root, owner.st_uid, owner.st_gid)
                    os.chown(backup, owner.st_uid, owner.st_gid)
            shutil.copy2(path, backup / name)
            fd, temporary = tempfile.mkstemp(prefix='.kit-upgrade-', dir=destination)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(content)
                os.chmod(temporary, path.stat().st_mode & 0o777)
                if hasattr(os, 'chown') and os.getuid() == 0:
                    owner = destination.stat()
                    os.chown(temporary, owner.st_uid, owner.st_gid)
                    os.chown(backup / name, owner.st_uid, owner.st_gid)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            print(f'Updated {name}; backup: {backup.name}/{name}')
            continue
        try:
            with path.open('xb') as stream:
                stream.write(content)
            # A root-run exporter must not leave an uneditable deployment kit.
            owner = destination.stat()
            if hasattr(os, 'chown') and os.getuid() == 0:
                os.chown(path, owner.st_uid, owner.st_gid)
            print(f'Created {name}')
        except FileExistsError:
            print(f'Preserved {name}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upgrade', action='store_true',
                        help='Update managed templates with backups; preserve deployment.env')
    args = parser.parse_args()
    export(Path('/bundle'), Path('/deployment/.project-intelligence-deploy'), upgrade=args.upgrade)

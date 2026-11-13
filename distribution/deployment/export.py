"""Export the deployment kit without overwriting operator-owned files."""
from pathlib import Path
import argparse
import os
import shutil
import stat
import tempfile
import json
import re

HELPERS = ('workspace-agent-go-LICENSE.txt', 'workspace-agent-build.txt', 'workspace-agent-linux-amd64', 'workspace-agent-windows-amd64.exe', 'workspace-agent-SHA256SUMS')
FILES = ('registry-preflight.sh', 'registry-preflight.ps1', 'container-cuda.ps1', 'assets-lock.json', 'asset-release.json', 'compose.assets.yaml', 'host-trust.sh', 'host-trust.ps1', 'compose.host-trust.yaml', 'wait-ready.sh', 'wait-ready.ps1', 'compose.workspace-volume.yaml', 'workspace.sh', 'workspace.ps1', 'workspace-autostart.sh', 'workspace-autostart.ps1', 'runtime-entrypoint.sh', 'runtime_supervisor.py', 'compose.ui-vulkan.yaml', 'compose.yaml', 'deployment.env', 'Makefile', 'start.sh', 'start.ps1', 'stop.ps1', 'README.md', 'compose.sh', 'compose.ps1', 'compose.accelerator.yaml', 'compose.vulkan.yaml', 'compose.cuda.yaml', 'compose.cpu.yaml', 'compose.windows-gpu.yaml', 'accelerator-lock.json', 'setup-windows-accelerator.ps1', 'url.sh', 'url.ps1', '.gitignore')


def migrate_environment(destination: Path, *, indexing=False, assets=False, dry_run=False):
    """Explicit selective migration; preserve all other operator bytes and modes."""
    path = destination / 'deployment.env'
    if path.is_symlink() or not path.is_file():
        raise ValueError('Migration requires a regular deployment.env')
    updates = {}
    if indexing:
        updates.update(PI_INDEX_ENGINE='resumable', PI_INDEX_PARALLEL='1', PI_EMBED_BATCHING='1')
    if assets:
        release = json.loads((destination / 'asset-release.json').read_text())
        manifest = destination / 'assets-lock.json'
        import hashlib
        if (release.get('release_status') != 'verified' or
            not re.fullmatch(r'ghcr\.io/shkirmantsev/project-intelligence-assets@sha256:[0-9a-f]{64}', release.get('image') or '') or
            not re.fullmatch(r'[0-9a-f]{64}', release.get('manifest_sha256') or '') or
            hashlib.sha256(manifest.read_bytes()).hexdigest() != release['manifest_sha256']):
            raise ValueError('Asset migration requires the verified published release and matching manifest')
        updates.update(PI_ASSET_IMAGE=release['image'], PI_ASSET_MANIFEST_SHA256=release['manifest_sha256'])
    original = path.read_bytes()
    content = original.decode('utf-8')
    newline = '\r\n' if '\r\n' in content else '\n'
    for key, value in updates.items():
        pattern = r'^' + key + r'=[^\r\n]*'
        if re.search(pattern, content, flags=re.M):
            content = re.sub(pattern, key + '=' + value, content, flags=re.M)
        else:
            if content and not content.endswith(('\r', '\n')):
                content += newline
            content += key + '=' + value + newline
        print(f'{"Preview" if dry_run else "Requested"}: {key}={value}')
    if dry_run or content.encode('utf-8') == original:
        return
    backup_root = destination / '.kit-backups'
    if backup_root.is_symlink():
        raise ValueError('Refusing symlinked kit backup directory')
    backup_root.mkdir(exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='environment-', dir=backup_root)) / path.name
    shutil.copy2(path, backup)
    descriptor, temporary = tempfile.mkstemp(prefix='.environment-', dir=destination)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copystat(path, temporary)
        if hasattr(os, 'chown') and os.getuid() == 0:
            owner = path.stat()
            os.chown(temporary, owner.st_uid, owner.st_gid)
            os.chown(backup, owner.st_uid, owner.st_gid)
            os.chown(backup.parent, owner.st_uid, owner.st_gid)
            os.chown(backup_root, owner.st_uid, owner.st_gid)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print('Environment backup: ' + str(backup))


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
    for name in FILES + HELPERS:
        _repair_root_owner(destination / name, owner)
    backup_root = destination / '.kit-backups'
    if backup_root.is_dir() and not backup_root.is_symlink():
        _repair_root_owner(backup_root, owner, directory=True)
        for backup in backup_root.glob('upgrade-*'):
            if backup.is_dir() and not backup.is_symlink():
                _repair_root_owner(backup, owner, directory=True)
                for name in FILES + HELPERS:
                    _repair_root_owner(backup / name, owner)


def export(source: Path, destination: Path, *, upgrade: bool = False) -> None:
    if destination.is_symlink():
        raise ValueError('Refusing symlinked kit destination')
    if upgrade:
        for name in FILES + HELPERS:
            if name != 'deployment.env' and (destination / name).is_symlink():
                raise ValueError(f'Refusing upgrade of managed symlink: {name}')
        if (destination / '.kit-backups').is_symlink():
            raise ValueError('Refusing symlinked kit backup directory')
    destination.mkdir(parents=True, exist_ok=True)
    _repair_kit_ownership(destination)
    backup = None
    for name in FILES + HELPERS:
        path = destination / name
        if name in HELPERS and not (source / name).exists():
            continue  # Source-only developer exports; release images contain all helpers.
        origin = source / name
        if name in ('asset-release.json', 'assets-lock.json') and not origin.exists():
            origin = source.parent / 'assets' / name
        content = origin.read_bytes()
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

    import json
    release_path = destination / 'asset-release.json'
    if release_path.is_file():
        release = json.loads(release_path.read_text(encoding='utf-8'))
        print('Kit revision: ' + str(release.get('kit_revision') or 'source/unbuilt'))
        print('Kit application image: ' + str(release.get('application_image') or 'source template'))
        print('Kit offline asset release: ' + str(release.get('image') or 'BLOCKED / unpublished'))
        print('Kit asset manifest: ' + str(release.get('manifest_sha256') or 'unavailable'))
        env_path = destination / 'deployment.env'
        if re.search(r'^PI_INDEX_ENGINE=legacy\s*$', env_path.read_text(encoding='utf-8'), re.M):
            print('WARNING: preserved legacy indexing. Preview --migrate-indexing --dry-run; apply --migrate-indexing for backed-up optimized defaults.')
        values = dict(line.split('=', 1) for line in env_path.read_text(encoding='utf-8').splitlines()
                      if line.startswith(('PI_ASSET_IMAGE=', 'PI_ASSET_MANIFEST_SHA256=', 'PI_IMAGE=')))
        requested_image = os.environ.get('PI_IMAGE') or values.get('PI_IMAGE')
        if requested_image and release.get('application_image') and requested_image != release['application_image']:
            print('WARNING: PI_IMAGE differs from the application image matched to this kit; verify compatibility before starting.')
        if (not values.get('PI_ASSET_IMAGE') or not values.get('PI_ASSET_MANIFEST_SHA256') or
            values['PI_ASSET_IMAGE'] != release.get('image') or values['PI_ASSET_MANIFEST_SHA256'] != release.get('manifest_sha256')):
            print('WARNING: offline asset pins are missing or differ from this kit. deployment.env was preserved; review it before starting. Online fallback is disabled.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upgrade', action='store_true',
                        help='Update managed templates with backups; preserve deployment.env')
    parser.add_argument('--migrate-indexing', action='store_true', help='Explicitly update only the three indexing defaults with backup')
    parser.add_argument('--migrate-assets', action='store_true', help='Explicitly reconcile only asset pins with the verified kit release')
    parser.add_argument('--dry-run', action='store_true', help='Preview selective environment migration without writing any files')
    args = parser.parse_args()
    destination = Path('/deployment/.project-intelligence-deploy')
    if args.dry_run and not (args.migrate_indexing or args.migrate_assets):
        parser.error('--dry-run requires a migration option')
    if not args.dry_run:
        export(Path('/bundle'), destination, upgrade=args.upgrade)
    if args.migrate_indexing or args.migrate_assets:
        migrate_environment(destination, indexing=args.migrate_indexing, assets=args.migrate_assets, dry_run=args.dry_run)

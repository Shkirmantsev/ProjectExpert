"""Export the deployment kit without overwriting operator-owned files."""
from pathlib import Path
import os

FILES = ('compose.yaml', 'deployment.env', 'Makefile', 'start.sh', 'start.ps1', 'stop.ps1', 'README.md', 'compose.sh', 'compose.ps1', 'compose.accelerator.yaml', 'compose.vulkan.yaml', 'compose.cuda.yaml', 'compose.cpu.yaml', 'compose.gemma-gguf.yaml', 'compose.windows-gpu.yaml', 'accelerator-lock.json', 'setup-windows-accelerator.ps1', '.gitignore')


def export(source: Path, destination: Path) -> None:
    if not destination.exists():
        destination.mkdir(parents=True)
        if hasattr(os, 'chown') and os.getuid() == 0:
            owner = destination.parent.stat()
            os.chown(destination, owner.st_uid, owner.st_gid)
    for name in FILES:
        path = destination / name
        content = (source / name).read_bytes()
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
    export(Path('/bundle'), Path('/deployment/.project-intelligence-deploy'))

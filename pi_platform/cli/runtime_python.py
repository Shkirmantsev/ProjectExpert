"""Provision the controller's stdlib Python from the pinned application image.

The CPU/Vulkan/CUDA runtime images need no Python installation or package manager.
Only the interpreter, its shared library and stdlib are copied, never site packages.
The product and sidecars are Linux amd64; the product's older glibc baseline runs
on the supported Ubuntu runtime bases. This is not a general Python distributor.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sys
import sysconfig
import tempfile
import uuid


def bundle_python(cache, *, executable=None, stdlib=None, library=None, version=None):
    executable=Path(executable or sys.executable).resolve()
    stdlib=Path(stdlib or sysconfig.get_path('stdlib'))
    library=Path(library or (Path(sysconfig.get_config_var('LIBDIR')) / sysconfig.get_config_var('INSTSONAME')))
    version=version or f'{sys.version_info.major}.{sys.version_info.minor}'
    identity=hashlib.sha256(executable.read_bytes()+library.read_bytes()+version.encode()).hexdigest()[:16]
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    destination=cache/('runtime-python-'+identity)
    if not destination.exists():
        stage=Path(tempfile.mkdtemp(prefix='.runtime-python-',dir=cache))
        try:
            (stage/'bin').mkdir()
            (stage/'lib').mkdir()
            shutil.copy2(executable,stage/'bin/python3')
            shutil.copy2(library,stage/'lib'/library.name)
            shutil.copytree(stdlib,stage/'lib'/('python'+version),ignore=shutil.ignore_patterns(
                'site-packages','dist-packages','__pycache__','test','tests',
                'ensurepip','idlelib','tkinter','config-*'))
            try:
                stage.rename(destination)
            except FileExistsError:
                pass  # Another setup process already published this same bundle.
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    link=cache/'runtime-python'
    temporary=cache/('.runtime-python-link-'+uuid.uuid4().hex)
    try:
        temporary.symlink_to(destination.name,target_is_directory=True)
        os.replace(temporary,link)
    finally:
        temporary.unlink(missing_ok=True)
    return link

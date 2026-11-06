"""Prepare private container caches, then run writers as the project owner.

Enabled by the application image, not by the host CLI. Never recursively chown
the repository; only derived private cache trees and the internal model key.
"""
import os
from pathlib import Path
import stat


def _repair_entry(path, owner):
    current=path.lstat()
    # lchown semantics preserve external symlink targets. Shared hard-linked
    # inodes cannot be reassigned without changing their other names.
    eligible=(stat.S_ISDIR(current.st_mode) or stat.S_ISLNK(current.st_mode) or
              stat.S_ISREG(current.st_mode) and current.st_nlink==1)
    if current.st_uid==0 and eligible:
        os.chown(path,owner.st_uid,owner.st_gid,follow_symlinks=False)


def _repair_tree(root, owner):
    if not root.exists() or root.is_symlink():
        return
    _repair_entry(root,owner)
    def failed(error):
        raise error
    for parent, directories, files in os.walk(root,followlinks=False,onerror=failed):
        for name in directories+files:
            _repair_entry(Path(parent)/name,owner)


def prepare_project_user(target, *, models_root=Path('/models')):
    if (os.environ.get('PI_RUN_AS_PROJECT_OWNER')!='1' or os.name!='posix'
            or os.geteuid()!=0 or target is None):
        return
    target=Path(target).resolve()
    owner=target.stat()
    if owner.st_uid==0:
        return  # A root-owned target cannot identify an ordinary project owner.
    cache=target/'.project-intelligence-cache'
    home=cache/'home'
    if cache.is_symlink() or home.is_symlink():
        raise ValueError('Private project cache and HOME must not be symlinks')
    home.mkdir(parents=True,exist_ok=True)
    _repair_tree(cache,owner)
    # Named model volume: root setup may have created a private 0600 API key
    # or HF/XDG state. Keep those usable after dropping application privileges.
    models_root=Path(models_root)
    if models_root.is_symlink():
        raise ValueError('Model volume root must not be a symlink')
    models_root.mkdir(exist_ok=True)
    _repair_entry(models_root,owner)
    for name in ('huggingface','cache'):
        _repair_tree(models_root/name,owner)
    key=models_root/'llama-api-key'
    if key.exists() and not key.is_symlink():
        _repair_entry(key,owner)
    os.environ['HOME']=str(home)
    os.setgroups([])
    os.setgid(owner.st_gid)
    os.setuid(owner.st_uid)

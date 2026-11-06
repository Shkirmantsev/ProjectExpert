"""Real root-to-user ownership regression using a cached Linux Python image."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = 'python:3.11-slim-bookworm@sha256:2333bd330d12de02514770b3585cad313644316047cdee24a7acfdece6de6efb'


@unittest.skipUnless(os.name == 'posix' and shutil.which('docker'), 'Linux Docker ownership test')
class DeploymentOwnershipTests(unittest.TestCase):
    def test_root_export_is_editable_and_removable_by_project_owner(self):
        image = None
        for candidate in (BASE, 'ghcr.io/shkirmantsev/project-intelligence-deployment:dev'):
            probe = subprocess.run(['docker','image','inspect',candidate], capture_output=True,timeout=20)
            if probe.returncode == 0:
                image = candidate
                break
        if image is None:
            self.skipTest('Pinned Python image not cached; no image download in unit tests')
        with tempfile.TemporaryDirectory() as raw:
            script = r'''
import importlib.util, os, shutil, subprocess, sys
from pathlib import Path
project=Path('/project');original_owner=project.stat()
if original_owner.st_uid==0:
    os.chown(project,12345,12346)  # Also exercise a normal user on root-run CI.
owner=project.stat()
spec=importlib.util.spec_from_file_location('kit', '/source/distribution/deployment/export.py')
kit=importlib.util.module_from_spec(spec);spec.loader.exec_module(kit)
dest=project/'.project-intelligence-deploy'
outside=project/'outside';outside.write_text('external evidence')
def assert_owner(path):
    actual=path.stat()
    assert (actual.st_uid,actual.st_gid)==(owner.st_uid,owner.st_gid), str(path)
def user_can_edit_and_remove():
    subprocess.run([sys.executable,'-c',
        "from pathlib import Path; import shutil; p=Path('/project/.project-intelligence-deploy'); "
        "f=p/'deployment.env'; f.write_text(f.read_text()+'\\noperator-edit=1\\n'); shutil.rmtree(p)"],
        user=owner.st_uid,group=owner.st_gid,extra_groups=[],check=True)
try:
    # Fresh root-run export.
    kit.export(Path('/source/distribution/deployment'),dest)
    assert_owner(dest);assert_owner(dest/'deployment.env')
    user_can_edit_and_remove()
    # A previous exporter or a bind-mount setup already created a root-owned kit.
    dest.mkdir(mode=0o700)
    (dest/'deployment.env').write_text('operator-setting=keep')
    (dest/'README.md').symlink_to(outside)
    (dest/'notes.txt').write_text('unrelated operator file')
    try:
        kit.export(Path('/source/distribution/deployment'),dest,upgrade=True)
    except ValueError:
        pass
    else:
        raise AssertionError('Upgrade must refuse managed symlinks')
    assert dest.stat().st_uid==0, 'Rejected upgrade must not mutate ownership'
    kit.export(Path('/source/distribution/deployment'),dest)
    assert_owner(dest);assert_owner(dest/'deployment.env')
    assert (dest/'deployment.env').read_text()=='operator-setting=keep'
    assert outside.stat().st_uid==0 and (dest/'notes.txt').stat().st_uid==0
    (dest/'start.sh').unlink();os.link(outside,dest/'start.sh')
    kit.export(Path('/source/distribution/deployment'),dest)
    assert outside.stat().st_uid==0, 'Hard-linked external ownership must be retained'
    (dest/'README.md').unlink()
    (dest/'README.md').write_text('old managed template')
    backups=dest/'.kit-backups'/'upgrade-old';backups.mkdir(parents=True)
    (backups/'README.md').write_text('old backup')
    kit.export(Path('/source/distribution/deployment'),dest,upgrade=True)
    for path in [dest, dest/'deployment.env', dest/'.kit-backups', backups, backups/'README.md']:
        assert_owner(path)
    for path in (dest/'.kit-backups').glob('upgrade-*/*'):
        assert_owner(path)
    assert outside.stat().st_uid==0 and (dest/'notes.txt').stat().st_uid==0
    user_can_edit_and_remove()
    # Do not steal an explicitly owned kit from another non-root operator.
    dest.mkdir();os.chown(dest,23456,23457)
    kit.export(Path('/source/distribution/deployment'),dest)
    assert (dest.stat().st_uid,dest.stat().st_gid)==(23456,23457)
    assert (dest/'deployment.env').stat().st_uid==23456
finally:
    if dest.exists():shutil.rmtree(dest)
    outside.unlink(missing_ok=True)
    os.chown(project,original_owner.st_uid,original_owner.st_gid)
'''
            result = subprocess.run(['docker','run','--rm','--network','none',
                '-v',str(ROOT)+':/source:ro','-v',raw+':/project',
                '--entrypoint','python',image,'-c',script], capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

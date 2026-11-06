"""Container identity prevents root-owned cache files across restarts."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]


class ContainerIdentityTests(unittest.TestCase):
    def test_cli_prepares_identity_before_dispatching_writer(self):
        from pi_platform.cli import main as cli
        calls=[]
        args=SimpleNamespace(command='ownership-fixture',target=Path('/repo'))
        with patch.object(cli,'_parse_args',return_value=args), \
             patch.dict(cli._DISPATCH,{'ownership-fixture':lambda _: calls.append('writer') or 0}), \
             patch('pi_platform.adapters.fs.container_identity.prepare_project_user',
                   side_effect=lambda target:calls.append(('identity',target))):
            self.assertEqual(cli.main([]),0)
        self.assertEqual(calls,[('identity',Path('/repo')),'writer'])
        self.assertIn('PI_RUN_AS_PROJECT_OWNER=1',(ROOT/'Containerfile').read_text())

    def test_host_cli_does_not_change_identity_or_ownership(self):
        from pi_platform.adapters.fs.container_identity import prepare_project_user
        with patch.dict(os.environ, {'PI_RUN_AS_PROJECT_OWNER':'0'}), \
             patch('os.setuid',create=True) as change:
            prepare_project_user(Path('/not-a-project'))
        change.assert_not_called()

    @unittest.skipUnless(os.name=='posix' and shutil.which('docker'), 'Linux Docker identity test')
    def test_existing_and_new_cache_files_belong_to_project_user(self):
        image='ghcr.io/shkirmantsev/project-intelligence-deployment:dev'
        if subprocess.run(['docker','image','inspect',image],capture_output=True,timeout=20).returncode:
            self.skipTest('Cached Python kit required; no image download')
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);project=root/'repo';models=root/'models'
            project.mkdir();models.mkdir()
            script=r'''
import importlib.util,os,subprocess,sys,shutil
from pathlib import Path
project=Path('/repo');original=project.stat()
if original.st_uid==0:os.chown(project,12345,12346)
owner=project.stat();cache=project/'.project-intelligence-cache'
outside=project/'outside';outside.write_text('unrelated root file')
cache.mkdir(mode=0o700);(cache/'old.json').write_text('preserved settings')
(cache/'linked').symlink_to(outside)
models=Path('/models');os.chown(models,0,0)
(models/'llama-api-key').write_text('fixture-internal-key');(models/'llama-api-key').chmod(0o600)
hf=models/'huggingface';hf.mkdir(mode=0o700);(hf/'cached-weights').write_text('reuse weights')
code=r"""
import importlib.util,os
from pathlib import Path
spec=importlib.util.spec_from_file_location('identity','/source/pi_platform/adapters/fs/container_identity.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.prepare_project_user(Path('/repo'))
assert os.geteuid()==Path('/repo').stat().st_uid!=0
cache=Path('/repo/.project-intelligence-cache')
assert (cache/'old.json').read_text()=='preserved settings'
assert Path('/models/llama-api-key').read_text()=='fixture-internal-key'
assert Path('/models/huggingface/cached-weights').read_text()=='reuse weights'
(cache/'new.json').write_text('new runtime state')
Path('/models/huggingface/new-weights').write_text('new download')
assert Path(os.environ['HOME']).is_relative_to(cache)
assert os.getgroups()==[]
"""
try:
    for _ in range(2):
        subprocess.run([sys.executable,'-m','pi_platform.cli','init-project','--target','/repo'],
                       env={**os.environ,'PYTHONPATH':'/source','PI_RUN_AS_PROJECT_OWNER':'1'},
                       cwd='/source',check=True)
        subprocess.run([sys.executable,'-c',code],env={**os.environ,'PI_RUN_AS_PROJECT_OWNER':'1'},check=True)
    assert all(p.lstat().st_uid==owner.st_uid for p in [cache,*cache.rglob('*')])
    assert outside.stat().st_uid==0 and outside.read_text()=='unrelated root file'
    subprocess.run([sys.executable,'-c',"import shutil; shutil.rmtree('/repo/.project-intelligence-cache')"],
                   user=owner.st_uid,group=owner.st_gid,extra_groups=[],check=True)
finally:
    if cache.exists():shutil.rmtree(cache)
    outside.unlink(missing_ok=True)
    for child in models.iterdir():
        if child.is_dir():shutil.rmtree(child)
        else:child.unlink()
    os.chown(project,original.st_uid,original.st_gid)
    os.chown(models,original.st_uid,original.st_gid)
'''
            result=subprocess.run(['docker','run','--rm','--network','none',
                '-v',str(ROOT)+':/source:ro','-v',str(project)+':/repo','-v',str(models)+':/models',
                '--entrypoint','python',image,'-c',script],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

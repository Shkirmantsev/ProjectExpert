import tempfile
import os
import shutil
from pathlib import Path
import unittest
from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery


class GeneratedWorktreeTests(unittest.TestCase):
    def test_generated_clones_are_pruned_but_authored_commands_and_worktrees_remain(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            names = ('src/a.java', '.claude/commands/help.md', 'docs/worktrees/guide.md',
                     '.claude/worktrees/copy/src/a.java', 'nested/.claude/worktrees/copy/a.sql',
                     'tmp/.claude/worktrees/copy/a.md', 'tmp/local/source/.claude/worktrees/copy/a.md')
            for name in names:
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('hello')
            self.assertEqual(set(RepositorySourceDiscovery().discover(root).paths()), set(names[:3]))

    @unittest.skipUnless(os.name != 'nt' and shutil.which('bash'), 'Linux Bash launcher fixture')
    def test_url_does_not_claim_index_ready_without_querying_readiness(self):
        import subprocess
        result = subprocess.run(['bash', 'distribution/deployment/url.sh'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Service URL:', result.stdout)
        self.assertIn('/health/ready', result.stdout)
        self.assertNotIn('Ready:', result.stdout)

    @unittest.skipUnless(os.name != 'nt' and shutil.which('bash'), 'Linux browser launcher fixture')
    def test_start_opens_only_the_resolved_url_without_status_text(self):
        import os
        import subprocess
        from tests.test_portable_deployment import _kit_copy, _fake_docker
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); kit = _kit_copy(raw)
            (kit / 'deployment.env').write_text('PI_CONTROL_PORT=9123\n')
            docker = _fake_docker(root)
            docker.write_text(docker.read_text().replace('exit 0',
                'case "$*" in *"port production 8765"*) printf "%s\\n" "127.0.0.1:9123";; esac\nexit 0'))
            opener = root / 'xdg-open'
            opener.write_text('#!/bin/sh\nprintf "%s" "$1" > "$OPENED_URL"\n')
            opener.chmod(0o755)
            output = root / 'opened-url'
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                   'CALLS': str(root / 'calls'), 'OPENED_URL': str(output), 'PI_OPEN_BROWSER': '1',
                   'PI_HOST_CA_MODE': 'off', 'PI_WORKSPACE_MODE': 'bind'}
            result = subprocess.run(['bash', str(kit / 'start.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_text(), 'http://localhost:9123/')

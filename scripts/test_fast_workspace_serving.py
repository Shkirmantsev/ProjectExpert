"""Synthetic Linux container acceptance: RO source, readiness, MCP and Wiki host writes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

IMAGE = os.environ.get('PI_FAST_WORKSPACE_TEST_IMAGE', 'projectexpert:fast-workspace-test')
AGENT = os.environ.get('PI_FAST_WORKSPACE_TEST_AGENT', '/tmp/workspace-agent-linux-amd64')


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


def main():
    with tempfile.TemporaryDirectory(prefix='projectexpert-fw-serving-') as raw:
        root = Path(raw)
        repo, kit = root / 'source', root / 'source' / '.project-intelligence-deploy'
        kit.mkdir(parents=True)
        (repo / 'README.md').write_text('# Stable workspace evidence\nA source imported into a read-only volume.\n')
        env = {**os.environ, 'PI_IMAGE': IMAGE}
        def agent(action):
            return run([AGENT, action, '--repo', str(repo), '--kit', str(kit)], env=env)
        agent('prepare'); agent('sync')
        config = json.loads((kit / 'workspace-agent.json').read_text())
        container = None
        try:
            args = ['docker', '--context', config['Context'], 'run', '--rm', '-d',
                    '--mount', f'type=volume,src={config["Workspace"]},dst=/repo,readonly',
                    '--mount', f'type=volume,src={config["Runtime"]},dst=/repo/.project-intelligence-cache',
                    '--mount', f'type=bind,src={repo / "project-knowledge"},dst=/repo/project-knowledge',
                    '-p', '127.0.0.1::8765', '-e', 'PI_STARTUP_PROFILE=minimal', '-e', 'PI_EMBEDDING_MODEL=hashing',
                    '-e', 'PI_DENSE_INDEX=flat', '-e', 'PI_DOCLING_ENABLED=0', '--entrypoint', 'python', IMAGE,
                    '-m', 'pi_platform.cli', 'start', '--target', '/repo', '--host', '0.0.0.0', '--port', '8765']
            container = run(args)
            address = 'http://' + run(['docker', 'port', container, '8765']).splitlines()[0]
            def request(path, body=None):
                data = json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(address + path, data=data, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    return json.load(response)
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    if request('/health/ready').get('ready'):
                        break
                except Exception:
                    pass
                time.sleep(.5)
            else:
                raise RuntimeError('Readiness failed: ' + run(['docker', 'logs', container]))
            status = request('/api/v1/indexing-status')
            assert status['ready'], status
            workspace = status['indexes']['workspace']
            assert workspace['sync_generation'] == workspace['indexed_sync_generation'], workspace
            tools = request('/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
            assert 'project.wiki_write_page' in {tool['name'] for tool in tools['result']['tools']}
            write = request('/mcp', {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
                'name': 'project.wiki_write_page', 'arguments': {'path': 'concept/host-durability',
                'title': 'Host durability', 'body': 'Canonical bytes are immediately visible at the original host path.'}}})
            page = repo / 'project-knowledge/wiki/concept/host-durability.md'
            assert page.is_file(), write
            assert 'Canonical bytes are immediately visible' in page.read_text()
            assert page.stat().st_uid == repo.stat().st_uid
            # Source is truly read-only even though runtime/canonical submounts are writable.
            rejected = subprocess.run(['docker', 'exec', container, 'python', '-c', "from pathlib import Path;Path('/repo/forbidden.txt').write_text('must fail')"], capture_output=True)
            assert rejected.returncode != 0
            assert not (repo / 'forbidden.txt').exists()
            run(['docker', 'restart', container])
            address = 'http://' + run(['docker', 'port', container, '8765']).splitlines()[0]
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    if request('/health/ready').get('ready'):
                        break
                except Exception:
                    pass
                time.sleep(.5)
            else:
                raise RuntimeError('Restart readiness failed')
            assert page.is_file()
            report = {'readiness': True, 'mcp_tool_discovery': True, 'wiki_host_write_through': True,
                      'wiki_project_owner': True, 'source_read_only': True, 'restart_readiness': True,
                      'model': 'diagnostic hashing/minimal (no GPU or semantic performance claim)'}
            print(json.dumps(report, indent=2))
        finally:
            if container:
                run(['docker', 'stop', '-t', '10', container])
            for name in ('Workspace', 'Runtime'):
                run(['docker', '--context', config['Context'], 'volume', 'rm', config[name]])


if __name__ == '__main__':
    main()

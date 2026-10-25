#!/usr/bin/env python3
"""Exercise the shipped deployment bundle with real model setup and restart."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def request(base, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--model-cache', type=Path, help='optional verified Q4 cache to reuse; omit for a cold-download test')
    parser.add_argument('--minimal', action='store_true', help='test common core only; never production inference evidence')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='pi-container-smoke-') as raw:
        root = Path(raw)
        repo = root / 'target repository'
        repo.mkdir()
        run('git', 'init', '-q', str(repo))
        run('git', '-C', str(repo), 'config', 'user.name', 'Container Smoke')
        run('git', '-C', str(repo), 'config', 'user.email', 'smoke@example.invalid')
        (repo / 'README.md').write_text('# Invoice service\nInvoices are reconciled by the billing service.\n')
        if not args.minimal:
            (repo / 'BillingService.java').write_text('package billing; public class BillingService { public int reconcileInvoice() { return 1; } }')
        run('git', '-C', str(repo), 'add', '.')
        run('git', '-C', str(repo), 'commit', '-qm', 'fixture')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {**os.environ, 'PI_IMAGE': args.image, 'PI_TARGET_REPO': str(repo),
               'PI_CONTROL_PORT': str(port), 'PI_EMBEDDING_MODEL': 'qwen-gguf',
               'PI_EMBEDDING_DEVICE': 'cpu', 'PI_DOCLING_ENABLED': '1'}
        compose = ['docker', 'compose', '--project-name', f'pi-smoke-{os.getpid()}',
                   '--env-file', str(ROOT / 'distribution/deployment/deployment.env'),
                   '-f', str(ROOT / 'distribution/deployment/compose.yaml')]
        if args.minimal:
            override = root / 'minimal.json'
            override.write_text(json.dumps({'services': {'production': {
                'environment': {'PI_STARTUP_PROFILE': 'minimal', 'PI_DOCLING_ENABLED': '0',
                                'PI_EMBEDDING_MODEL': 'hashing', 'PI_DENSE_INDEX': 'flat'}
            }}}))
            compose.extend(['-f', str(override)])
            run('docker', 'run', '--rm', '-v', f'{repo}:/repo', args.image,
                'init-project', '--target', '/repo')
        else:
            compose.extend(['-f', str(ROOT / 'distribution/deployment/compose.accelerator.yaml'),
                            '-f', str(ROOT / 'distribution/deployment/compose.cpu.yaml')])
        base = f'http://127.0.0.1:{port}'
        try:
            if args.model_cache and not args.minimal:
                # Seed only model bytes; setup still checks their hash and creates its own key.
                volume = f'pi-smoke-{os.getpid()}_model-cache'
                run(*compose, 'create', 'model-setup', env=env)
                run('docker', 'run', '--rm', '--entrypoint', 'python',
                    '-v', str(args.model_cache.resolve()) + ':/seed:ro', '-v', volume + ':/models',
                    args.image, '-c',
                    'from pi_platform.adapters.retrieval.gguf_artifacts import FILENAME; '
                    'import shutil; shutil.copyfile("/seed/"+FILENAME, "/models/"+FILENAME)')
            run(*compose, 'up', '-d', '--wait', '--wait-timeout', str(args.timeout), env=env)
            assert request(base, '/health/ready')['ready']
            with urllib.request.urlopen(base + '/', timeout=10) as page:
                assert b'Project Intelligence' in page.read()
            result = request(base, '/api/v1/query', {'text': 'invoice billing', 'top_k': 3})
            assert result.get('results'), result
            status = request(base, '/api/v1/indexing-status')
            assert status['indexes']['cache_entries'] > 0, status
            if not args.minimal:
                assert not status['indexes']['retrieval']['source_failures'], status
            version = request(base, '/api/v1/project-version')
            assert version['fingerprint'] and version['embedding_model_version'], version
            tools = request(base, '/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
            assert 'project.search' in json.dumps(tools), tools
            run(*compose, 'exec', '-T', 'production', 'python', '-m', 'pip', 'check', env=env)
            run(*compose, 'restart', env=env)
            # A fresh healthcheck after restart must establish readiness again.
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                try:
                    if request(base, '/health/ready')['ready']:
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(2)
            else:
                raise RuntimeError('Restart did not reach readiness')
            assert request(base, '/api/v1/query', {'text': 'invoice billing'}).get('results')
            profile = 'minimal core only' if args.minimal else 'real model setup'
            print(f'PASS: {profile}, readiness, query, UI, MCP, dependency check and restart')
        finally:
            subprocess.run([*compose, 'logs', '--tail', '80'], env=env)
            subprocess.run([*compose, 'down', '-v'], env=env)
            # Container-generated fixture files can be root-owned on Linux.
            subprocess.run(['docker', 'run', '--rm', '--entrypoint', 'python',
                            '-v', f'{repo}:/repo', args.image, '-c',
                            'import pathlib,shutil; '
                            '[shutil.rmtree(p) for p in pathlib.Path("/repo").iterdir() if p.is_dir()]'])


if __name__ == '__main__':
    main()

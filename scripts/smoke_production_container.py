#!/usr/bin/env python3
"""Exercise the shipped deployment bundle with real model setup and restart."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


class ContainerEndpoint:
    """Use an in-network HTTP client; an internal bridge need not expose ports."""
    def __init__(self, container):
        self.container = container

    def fetch(self, path, payload=None):
        program = ("import json,sys,urllib.request; "
                   "body=None if sys.argv[2]=='null' else sys.argv[2].encode(); "
                   "request=urllib.request.Request('http://127.0.0.1:8765'+sys.argv[1],data=body,headers={'Content-Type':'application/json'}); "
                   "response=urllib.request.urlopen(request,timeout=60); sys.stdout.buffer.write(response.read())")
        result = subprocess.run(['docker','exec',self.container,'python','-c',program,path,json.dumps(payload)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
        if result.returncode:
            raise RuntimeError('In-network HTTP request failed: ' + result.stderr.decode(errors='replace')[-4096:])
        return result.stdout


def request_bytes(base, path, payload=None):
    if isinstance(base, ContainerEndpoint):
        return base.fetch(path, payload)
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def request(base, path, payload=None):
    try:
        return json.loads(request_bytes(base, path, payload))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{path}: HTTP {exc.code}: {exc.read(4096).decode(errors='replace')}") from exc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--candidate-assets', action='store_true', help='Explicit local-only acceptance using a Docker image ID; does not certify registry publication')
    parser.add_argument('--asset-image')
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--minimal', action='store_true', help='test common core only; never production inference evidence')
    args = parser.parse_args()
    if args.candidate_assets and args.minimal:
        parser.error('Local asset acceptance cannot be combined with the model-free minimal smoke')
    if args.candidate_assets:
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.asset_image or '') or not re.fullmatch(r'[0-9a-f]{64}', args.manifest_sha256 or ''):
            parser.error('Local acceptance requires the actual immutable Docker image ID and independent manifest SHA-256')
        actual = subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',args.asset_image],text=True).strip()
        if actual != args.asset_image:
            parser.error('Local candidate image identity mismatch')
        print('LOCAL CANDIDATE ACCEPTANCE: published OCI identity remains unverified')
    elif not args.minimal:
        import sys
        sys.path.insert(0, str(ROOT))
        from pi_platform.deployment.offline_assets import release_identity
        identity = release_identity(ROOT / 'distribution/assets/asset-release.json')
        if args.asset_image and args.asset_image != identity['image']:
            parser.error('Asset image differs from the independently reviewed release')
        if args.manifest_sha256 and args.manifest_sha256 != identity['manifest_sha256']:
            parser.error('Asset manifest differs from the independently reviewed release')
        args.asset_image, args.manifest_sha256 = identity['image'], identity['manifest_sha256']
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
        (repo / 'pyproject.toml').write_text('[project]\nname = "billing"\ndependencies = ["httpx>=0.27"]\n')
        (repo / 'billing.py').write_text('def reconcile_invoice(invoice_id: str):\n    """Reconcile an invoice using the billing service."""\n    return invoice_id\n')
        run('git', '-C', str(repo), 'add', '.')
        run('git', '-C', str(repo), 'commit', '-qm', 'fixture')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {**os.environ, 'PI_IMAGE': args.image, 'PI_TARGET_REPO': str(repo),
               'PI_CONTROL_PORT': str(port), 'PI_EMBEDDING_MODEL': 'gemma',
               'PI_EMBEDDING_DEVICE': 'cpu', 'PI_DOCLING_ENABLED': '1',
               'PI_ASSET_IMAGE': args.asset_image or args.image,
               'PI_ASSET_MANIFEST_SHA256': args.manifest_sha256 or '0' * 64}
        # Acceptance exercises the fresh optimized profile even when the caller
        # uses explicit legacy overrides in their own deployment.
        env.update(PI_INDEX_ENGINE='resumable', PI_INDEX_PARALLEL='1', PI_EMBED_BATCHING='1')
        compose = ['docker', 'compose', '--project-name', f'pi-smoke-{os.getpid()}',
                   '--env-file', str(ROOT / 'distribution/deployment/deployment.env'),
                   '-f', str(ROOT / 'distribution/deployment/compose.yaml')]
        if args.minimal:
            override = root / 'minimal.json'
            override.write_text(json.dumps({'services': {'production': {
                'environment': {'PI_STARTUP_PROFILE': 'minimal', 'PI_DOCLING_ENABLED': '0',
                                'PI_EMBEDDING_MODEL': 'hashing', 'PI_DENSE_INDEX': 'flat', 'PI_REQUIRE_OFFLINE_ASSETS':'0'}
            }, 'asset-seed': {'image':args.image, 'entrypoint':['python', '-c', 'pass'], 'command':[]}}}))
            compose.extend(['-f', str(override)])
            run('docker', 'run', '--rm', '-v', f'{repo}:/repo', args.image,
                'init-project', '--target', '/repo')
        else:
            compose.extend(['-f', str(ROOT / 'distribution/deployment/compose.accelerator.yaml'),
                            '-f', str(ROOT / 'distribution/deployment/compose.cpu.yaml')])
        base = f'http://127.0.0.1:{port}'
        try:
            if not args.minimal:
                # Pull all registry dependencies before denying runtime egress.
                if args.candidate_assets:
                    run(*compose, 'pull', 'embeddings', env=env)
                else:
                    run(*compose, 'pull', 'asset-seed', 'embeddings', env=env)
                denied = root / 'egress-denied.json'
                denied.write_text(json.dumps({'networks': {'default': {'internal': True}}}))
                compose.extend(['-f', str(denied)])
            run(*compose, 'up', '-d', '--wait', '--wait-timeout', str(args.timeout), env=env)
            if not args.minimal:
                container = subprocess.check_output([*compose, 'ps', '-q', 'production'], env=env, text=True).strip()
                base = ContainerEndpoint(container)
                for directory in ('tests', 'scripts'):
                    run('docker', 'exec', container, 'mkdir', '-p', '/tmp/offline-acceptance/' + directory)
                for name in ('tests/__init__.py', 'tests/test_docling_production_binding.py',
                             'scripts/generate_pdf_fixtures.py', 'scripts/verify_offline_runtime.py'):
                    run('docker', 'cp', str(ROOT / name), container + ':/tmp/offline-acceptance/' + name)
                run(*compose, 'exec', '-T', '-e', 'PI_RUN_PDF_TESTS=1', '-e', 'PYTHONPATH=/tmp/offline-acceptance',
                    'production', 'python', '/tmp/offline-acceptance/scripts/verify_offline_runtime.py', env=env)
            assert request(base, '/health/ready')['ready']
            assert b'Project Intelligence' in request_bytes(base, '/')
            result = request(base, '/api/v1/query', {'text': 'invoice billing', 'top_k': 3})
            assert result.get('results'), result
            python_result = request(base, '/api/v1/query', {'text': 'httpx Python billing dependency', 'top_k': 10})
            assert 'httpx' in json.dumps(python_result).lower(), python_result
            status = request(base, '/api/v1/indexing-status')
            assert status['indexes']['cache_entries'] > 0, status
            if not args.minimal:
                assert not status['indexes']['retrieval']['source_failures'], status
                assert status['indexes']['retrieval']['index_engine'] == 'resumable', status
            version = request(base, '/api/v1/project-version')
            assert version['fingerprint'] and version['embedding_model_version'], version
            tools = request(base, '/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
            assert 'project.search' in json.dumps(tools), tools
            discovered = request(base, '/mcp', {'jsonrpc': '2.0', 'id': 'skills-discover',
                'method': 'server/discover'})['result']
            assert 'io.modelcontextprotocol/skills' in discovered['capabilities']['extensions']
            skills = request(base, '/mcp', {'jsonrpc': '2.0', 'id': 'skills-list',
                'method': 'skills/list'})['result']['skills']
            entry = next(skill for skill in skills if skill['uri'] == 'skill://project-intelligence/SKILL.md')
            fetched = request(base, '/mcp', {'jsonrpc': '2.0', 'id': 'skills-get',
                'method': 'skills/get', 'params': {'uri': entry['uri']}})['result']['skill']
            assert fetched == entry
            for resource in entry['resources']:
                content = request(base, '/mcp', {'jsonrpc': '2.0', 'id': 'skills-read',
                    'method': 'resources/read', 'params': {'uri': resource['uri']}})['result']['contents'][0]
                raw = content['text'].encode('utf-8')
                assert len(raw) == resource['size']
                assert 'sha256:' + hashlib.sha256(raw).hexdigest() == resource['digest']
            run(*compose, 'exec', '-T', 'production', 'python', '-m', 'pip', 'check', env=env)
            request(base, '/mcp', {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                'params': {'name': 'project.wiki_write_page', 'arguments': {
                    'path': 'invoice-overview.md', 'title': 'Invoice overview',
                    'body': 'The billing service reconciles invoices. Source: README.md.'}}})
            page = repo / 'project-knowledge/wiki/invoice-overview.md'
            assert page.is_file(), 'MCP Wiki write did not create its page'
            assert 'The billing service reconciles invoices.' in page.read_text()
            if os.name == 'posix':
                assert page.stat().st_uid == repo.stat().st_uid
                assert stat.S_IMODE(page.stat().st_mode) == 0o644
            run(*compose, 'restart', env=env)
            # A fresh healthcheck after restart must establish readiness again.
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                try:
                    if request(base, '/health/ready')['ready']:
                        break
                except (OSError, ValueError, RuntimeError):
                    pass
                time.sleep(2)
            else:
                raise RuntimeError('Restart did not reach readiness')
            assert request(base, '/api/v1/query', {'text': 'invoice billing'}).get('results')
            if os.name == 'posix':
                cache = repo / '.project-intelligence-cache'
                for path in [cache, *cache.rglob('*')]:
                    try:
                        owner = path.lstat().st_uid
                    except FileNotFoundError:  # transient SQLite journal
                        continue
                    assert owner == repo.stat().st_uid, f'Cache owner differs: {path}'
                # Exercise another atomic update after restart as well.
                request(base, '/mcp', {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                    'params': {'name': 'project.wiki_write_page', 'arguments': {
                        'path': 'invoice-overview.md', 'title': 'Invoice overview',
                        'body': 'Updated invoice explanation. Source: README.md.'}}})
                assert 'Updated invoice explanation.' in page.read_text()
                assert page.stat().st_uid == repo.stat().st_uid
                assert stat.S_IMODE(page.stat().st_mode) == 0o644
            profile = 'minimal core only' if args.minimal else 'egress-denied immutable asset setup'
            if not args.minimal:
                logs = subprocess.check_output([*compose, 'logs', '--no-color'], env=env, text=True)
                assert not re.search(r'https?://(?:[a-z0-9-]+\.)?(?:huggingface\.co|hf\.co)', logs, re.I), 'Unexpected Hugging Face request in offline logs'
            print(f'PASS: {profile}, readiness, query, UI, MCP, dependency check and restart')
        finally:
            subprocess.run([*compose, 'logs', '--tail', '80'], env=env)
            subprocess.run([*compose, 'down', '-v'], env=env)
            # Restore ownership only on this TemporaryDirectory fixture. Python's
            # context manager then removes its own temporary tree on the host.
            if hasattr(os, 'getuid'):
                subprocess.run(['docker', 'run', '--rm', '--entrypoint', 'chown',
                                '-v', f'{repo}:/fixture', args.image,
                                '-R', f'{os.getuid()}:{os.getgid()}', '/fixture'])



if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Resolve reviewed CI assets; upstream assembly is explicit and builder-only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pi_platform.deployment.asset_pack import AssetPackError, load_manifest, local_file, sha256
from pi_platform.deployment.offline_assets import COMPATIBILITY, release_identity

ASSET_REPOSITORY = 'ghcr.io/shkirmantsev/project-intelligence-assets'


def reviewed_inventory(root: Path):
    assets = root / 'distribution/assets'
    # Git-reviewed inventory bytes are the input, never a manually copied hash.
    digest = sha256(assets / 'assets-lock.json')
    manifest = load_manifest(assets / 'assets-lock.json', digest)
    if manifest['runtime_compatibility'] != COMPATIBILITY:
        raise AssetPackError('CI asset inventory is incompatible with this runtime')
    if manifest.get('production_lock_sha256') != sha256(root / 'requirements-production-linux-x86_64.txt'):
        raise AssetPackError('CI asset inventory does not match the production dependency lock')
    backends = manifest.get('native_backends')
    if not isinstance(backends, list) or not backends or any(value not in ('cuda', 'vulkan') for value in backends) or len(set(backends)) != len(backends):
        raise AssetPackError('CI asset inventory must declare native backends')
    for row in manifest['files']:
        if row['path'].startswith('licenses/') and sha256(local_file(assets, row['path'])) != row['sha256']:
            raise AssetPackError('CI retained license evidence checksum mismatch: ' + row['path'])
    return digest, manifest


def verify_image(root: Path, image: str, digest: str) -> bool:
    """Current verifier, not the potentially stale verifier bundled in the image."""
    program = '''from pathlib import Path
import sys
from pi_platform.deployment.offline_assets import verify_pack
from pi_platform.deployment.asset_pack import AssetPackError
try:
    verify_pack(Path('/opt/projectexpert-assets'), sys.argv[1])
except (AssetPackError, OSError, ValueError) as exc:
    print('Asset payload mismatch:', exc, file=sys.stderr)
    sys.exit(42)
'''
    result = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'python',
        '-v', str(root / 'pi_platform') + ':/opt/current-verifier/pi_platform:ro',
        '-v', str(root / 'requirements-production-linux-x86_64.txt') + ':/opt/current-verifier/requirements-production-linux-x86_64.txt:ro',
        '-e', 'PYTHONPATH=/opt/current-verifier', '-e', 'PI_PLATFORM_HOME=/opt/current-verifier',
        image, '-c', program, digest], cwd=root)
    if result.returncode not in (0, 42):
        raise AssetPackError('Asset verifier could not run; check Docker/runner diagnostics (exit ' + str(result.returncode) + ')')
    return result.returncode == 0


def registry_identity(root: Path, image: str) -> str:
    references = json.loads(subprocess.check_output(
        ['docker', 'image', 'inspect', '--format', '{{json .RepoDigests}}', image], cwd=root, text=True))
    for reference in references or []:
        if re.fullmatch(re.escape(ASSET_REPOSITORY) + r'@sha256:[0-9a-f]{64}', reference):
            return reference
    raise AssetPackError('Published asset lacks an actual matching registry RepoDigest')


def published_values(root: Path, image: str, digest: str, release_dir: Path) -> dict:
    """Persist generated release evidence, without rewriting source metadata."""
    if not re.fullmatch(re.escape(ASSET_REPOSITORY) + r'@sha256:[0-9a-f]{64}', image):
        raise AssetPackError('Expected an immutable published asset reference, not a tag or local image ID')
    subprocess.run(['docker', 'pull', image], cwd=root, check=True)
    if not verify_image(root, image, digest):
        raise AssetPackError('Published immutable asset failed current payload verification')
    release_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / 'distribution/assets/assets-lock.json', release_dir / 'assets-lock.json')
    record = dict(schema_version=1, release_status='verified', image=image, manifest_sha256=digest,
                  reason='CI observed published RepoDigest and verified the reviewed payload; application promotion still requires offline acceptance')
    path = release_dir / 'asset-release.json'
    path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    release_identity(path)
    return dict(PI_ASSET_IMAGE=image, PI_ASSET_MANIFEST_SHA256=digest, PI_ASSET_MODE='published',
                PI_ASSET_RELEASE_FILE=str(path.resolve()))


def ensure_published(root: Path, release_dir: Path) -> dict:
    digest, _ = reviewed_inventory(root)  # Reject missing review before network/download work.
    tag = ASSET_REPOSITORY + ':manifest-' + digest
    pull = subprocess.run(['docker', 'pull', tag], cwd=root, capture_output=True, text=True)
    if pull.returncode == 0:
        image = registry_identity(root, tag)
        if verify_image(root, image, digest):
            return published_values(root, image, digest, release_dir)
    else:
        # A denied/private registry, TLS failure or timeout is not missing models.
        failure = (pull.stderr + '\n' + pull.stdout).lower()
        denied = ('unauthorized', 'denied', 'forbidden', 'credential', 'certificate', 'x509',
                  'timeout', 'timed out', 'connection refused', 'no such host', 'deadline exceeded')
        absent = any(marker in failure for marker in ('manifest unknown', 'manifest_unknown', 'name unknown', 'name_unknown'))
        absent = absent or (tag.lower() in failure and 'not found' in failure)
        if (any(marker in failure for marker in denied) or
            re.search(r'\b(?:401|403|429|5\d\d)\b', failure) or not absent):
            raise AssetPackError('Cannot inspect asset registry; check GHCR package access, Docker login, TLS and network. No upstream assembly attempted.')
    candidate = prepare(root, candidate=True)
    subprocess.run(['docker', 'tag', candidate['PI_ASSET_IMAGE'], tag], cwd=root, check=True)
    subprocess.run(['docker', 'push', tag], cwd=root, check=True)
    return published_values(root, registry_identity(root, tag), digest, release_dir)


def prepare(root: Path, *, candidate=False) -> dict:
    assets = root / 'distribution/assets'
    if not candidate:
        release = release_identity(assets / 'asset-release.json')
        subprocess.run(['docker', 'pull', release['image']], cwd=root, check=True)
        return dict(PI_ASSET_IMAGE=release['image'], PI_ASSET_MANIFEST_SHA256=release['manifest_sha256'], PI_ASSET_MODE='published',
                    PI_ASSET_RELEASE_FILE=str(assets / 'asset-release.json'))

    # Candidate inspection never changes the canonical publication metadata.
    digest, manifest = reviewed_inventory(root)
    backends = manifest.get('native_backends')
    pack = root / 'tmp/local/asset-pack'
    if pack.exists():
        raise AssetPackError('CI asset build directory already exists; refusing to overwrite or remove it')
    subprocess.run([sys.executable, 'scripts/materialize_asset_pack.py', '--output', str(pack),
                    '--reviewed-manifest', str(assets / 'assets-lock.json'),
                    '--reviewed-manifest-sha256', digest, '--license-evidence', str(assets / 'licenses'),
                    '--native-backends', *backends], cwd=root, check=True)
    subprocess.run(['docker', 'build', '-f', 'distribution/assets/Containerfile', '--target', 'verified',
                    '--build-arg', 'PI_ASSET_MANIFEST_SHA256=' + digest,
                    '-t', 'projectexpert-assets:ci-candidate', '.'], cwd=root, check=True)
    image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}',
                                     'projectexpert-assets:ci-candidate'], cwd=root, text=True).strip()
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise AssetPackError('CI candidate lacks an actual immutable Docker image ID')
    # This directory was created only by this invocation; the image retains it.
    # Remove the extra multi-gigabyte copy before production build/model seeding.
    shutil.rmtree(pack)
    return dict(PI_ASSET_IMAGE=image, PI_ASSET_MANIFEST_SHA256=digest, PI_ASSET_MODE='candidate')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--candidate', action='store_true', help='Explicit unpublished PR verification, never release promotion')
    modes.add_argument('--ensure-published', action='store_true', help='Trusted release builder only: reuse or build/publish reviewed assets')
    modes.add_argument('--published-image', help='Use the actual immutable output of the asset publication job')
    parser.add_argument('--env-output', type=Path, required=True)
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--release-dir', type=Path, default=ROOT / 'tmp/local/ci-assets')
    args = parser.parse_args()
    if args.ensure_published:
        values = ensure_published(ROOT, args.release_dir.resolve())
    elif args.published_image:
        digest, _ = reviewed_inventory(ROOT)
        values = published_values(ROOT, args.published_image, digest, args.release_dir.resolve())
    else:
        values = prepare(ROOT, candidate=args.candidate)
    content = ''.join(f'{key}={value}\n' for key, value in values.items())
    args.env_output.parent.mkdir(parents=True, exist_ok=True)
    args.env_output.write_text(content)
    if args.github_output:
        with args.github_output.open('a') as stream:
            stream.write(content)


if __name__ == '__main__':
    main()

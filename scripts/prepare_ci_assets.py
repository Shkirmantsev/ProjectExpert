#!/usr/bin/env python3
"""Prepare reviewed PR assets explicitly; default mode requires a published release."""
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
from pi_platform.deployment.offline_assets import release_identity


def prepare(root: Path, *, candidate=False) -> dict:
    assets = root / 'distribution/assets'
    if not candidate:
        release = release_identity(assets / 'asset-release.json')
        subprocess.run(['docker', 'pull', release['image']], cwd=root, check=True)
        return dict(PI_ASSET_IMAGE=release['image'], PI_ASSET_MANIFEST_SHA256=release['manifest_sha256'], PI_ASSET_MODE='published')

    # Candidate inspection never changes the canonical publication metadata.
    digest = json.loads((assets / 'asset-release.json').read_text())['manifest_sha256'] or ''
    manifest = load_manifest(assets / 'assets-lock.json', digest)
    if manifest.get('production_lock_sha256') != sha256(root / 'requirements-production-linux-x86_64.txt'):
        raise AssetPackError('CI asset inventory does not match the production dependency lock')
    backends = manifest.get('native_backends')
    if not isinstance(backends, list) or not backends or any(value not in ('cuda', 'vulkan') for value in backends) or len(set(backends)) != len(backends):
        raise AssetPackError('CI asset inventory must declare native backends')
    for row in manifest['files']:
        if row['path'].startswith('licenses/') and sha256(local_file(assets, row['path'])) != row['sha256']:
            raise AssetPackError('CI retained license evidence checksum mismatch: ' + row['path'])
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
    parser.add_argument('--candidate', action='store_true', help='Explicit unpublished PR verification, never release promotion')
    parser.add_argument('--env-output', type=Path, required=True)
    args = parser.parse_args()
    values = prepare(ROOT, candidate=args.candidate)
    args.env_output.write_text(''.join(f'{key}={value}\n' for key, value in values.items()))


if __name__ == '__main__':
    main()

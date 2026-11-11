"""Merge public CA roots without weakening HTTPS verification."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import ssl
import tempfile


def merge_ca_bundles(image_bundle: Path, extra_bundles: list[Path], destination: Path) -> dict:
    certificates: dict[str, str] = {}
    imported = set()
    for index, path in enumerate([image_bundle, *extra_bundles]):
        text = path.read_text(encoding='ascii')
        if 'PRIVATE KEY' in text:
            raise ValueError('CA bundles must contain public certificates only')
        blocks = re.findall(r'-----BEGIN CERTIFICATE-----\s+.*?-----END CERTIFICATE-----', text, re.S)
        if not blocks:
            raise ValueError(f'CA bundle contains no certificates: {path}')
        # Have OpenSSL validate each input bundle, preserving strict verification.
        ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cadata=text)
        for block in blocks:
            der = ssl.PEM_cert_to_DER_cert(block)
            fingerprint = hashlib.sha256(der).hexdigest()
            certificates[fingerprint] = block + '\n'
            if index:
                imported.add(fingerprint)
    content = ''.join(certificates.values()).encode('ascii')
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.ca-', dir=destination.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'certificates': len(certificates), 'imported_certificates': len(imported), 'sha256': hashlib.sha256(content).hexdigest()}


def configure_container_trust() -> dict:
    mode = os.environ.get('PI_HOST_CA_MODE', 'auto')
    if mode not in ('auto', 'off'):
        raise ValueError('PI_HOST_CA_MODE must be auto or off')
    if mode == 'off':
        return {'enabled': False}
    extra = []
    host = Path('/run/projectexpert-host-trust/host-ca-bundle.pem')
    if host.is_file():
        extra.append(host)
    explicit = os.environ.get('PI_EXTRA_CA_BUNDLE')
    if explicit:
        extra.append(Path(explicit))
    if not extra:
        return {'enabled': False}
    output = Path('/run/projectexpert/ca-bundle.pem')
    result = merge_ca_bundles(Path('/etc/ssl/certs/ca-certificates.crt'), extra, output)
    for key in ('SSL_CERT_FILE', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE'):
        os.environ[key] = str(output)
    return {'enabled': True, **result}

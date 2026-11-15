"""Conservative outward admission; local indexing never uses this filter."""
from pathlib import PurePosixPath
import re

POLICY_VERSION = 'safe-source-export/1'
PROTECTED_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.jks', '.keystore', '.crt', '.cer'}
SECRET = re.compile(
    r'-----BEGIN (?:[A-Z0-9 ]*PRIVATE KEY|CERTIFICATE)-----|'
    r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16})|'
    r'(?i:\b(?:password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret|authorization)'
    r'\s*[=:]\s*[\"\']?[^\s\"\'<>]{4,})|(?i:\bbearer\s+[a-z0-9._~-]{12,})'
)


def protected_path(path):
    name = PurePosixPath(path).name.lower()
    return (PurePosixPath(path).suffix.lower() in PROTECTED_SUFFIXES
            or name == '.env' or name.startswith('.env.')
            or name in {'credentials', 'id_rsa', 'id_ed25519', 'id_ecdsa'})


def sensitive_text(text):
    return bool(SECRET.search(text))


def restricted_derivation(value):
    """Last-mile generated output guard, including declared restrictions."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {'securityClassification', 'security_class'} and item is not None:
                if not isinstance(item, str) or item.lower() not in {'public', 'unclassified'}:
                    return True
            if key == 'policy' and item is not None and (not isinstance(item, str) or item not in {'', 'SNAPSHOT'}):
                return True
            if key.lower() in {'password', 'secret', 'api_key', 'apikey', 'access_token', 'authorization', 'auth_token', 'refresh_token'} and item:
                return True
            if restricted_derivation(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(restricted_derivation(item) for item in value)
    elif isinstance(value, str):
        return sensitive_text(value)
    return False


def diagnostic_source(source):
    metadata = getattr(source, 'metadata', None)
    if metadata is None:
        return 'protected-source'
    policy = str(getattr(metadata, 'policy', None) or '').upper()
    classification = str(getattr(metadata, 'securityClassification', None) or 'unclassified').lower()
    if (policy not in {'', 'SNAPSHOT'} or classification not in {'public', 'unclassified'}
            or sensitive_text(source.id)):
        return 'protected-source'
    return source.id


def sensitive_file(path):
    # Bounded streaming with overlap for recognizers spanning read boundaries.
    tail = ''
    with path.open('rb') as handle:
        while raw := handle.read(1024 * 1024):
            text = tail + raw.decode('utf-8', errors='replace')
            if sensitive_text(text):
                return True
            tail = text[-4096:]
    return False

"""Reviewed, deterministic fallback charsets; original source bytes are never changed."""
from dataclasses import dataclass
import codecs
import json
from pathlib import Path
import re

POLICY_PATH = Path('config/source-encodings.json')
_ALLOWED = {codecs.lookup(name).name for name in (
    'cp1250', 'cp1251', 'cp1252', 'cp1253', 'cp1254', 'cp1255', 'cp1256', 'cp1257', 'cp1258',
    'iso-8859-1', 'iso-8859-2', 'iso-8859-5', 'iso-8859-7', 'iso-8859-9', 'iso-8859-15',
    'koi8-r', 'koi8-u', 'cp866', 'shift_jis', 'cp932', 'gb18030', 'big5', 'euc-kr', 'euc-jp')}


def supported_legacy_encodings():
    return sorted(_ALLOWED)


def canonical_path(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or any(ord(c) < 32 for c in value):
        raise ValueError('Source encoding paths must be repository-relative POSIX paths')
    if any(part in ('', '.', '..') for part in value.split('/')):
        raise ValueError('Source encoding paths cannot contain traversal or empty components')
    return value


def _pattern(value):
    canonical_path(value)
    if len(value) > 512 or value.count('**') > 8:
        raise ValueError('Source encoding pattern is too complex')
    # **/ matches zero or more directories; * never crosses a separator.
    expression = re.escape(value).replace(r'\*\*/', '(?:.*/)?').replace(r'\*\*', '.*').replace(r'\*', '[^/]*').replace(r'\?', '[^/]')
    return re.compile('^' + expression + '$')


@dataclass(frozen=True)
class SourceDecodingPolicy:
    rules: tuple = ()

    @classmethod
    def from_dict(cls, payload):
        if not isinstance(payload, dict) or payload.get('schema_version') != 1 or payload.get('default_encoding', 'utf-8') != 'utf-8':
            raise ValueError('Source encoding policy requires schema_version=1 and default_encoding=utf-8')
        rules = payload.get('rules', [])
        if not isinstance(rules, list) or len(rules) > 256:
            raise ValueError('Source encoding policy requires at most 256 rules')
        parsed = []
        for rule in rules:
            if not isinstance(rule, dict) or not isinstance(rule.get('encoding'), str):
                raise ValueError('Each source encoding rule requires pattern and encoding')
            try:
                codec = codecs.lookup(rule['encoding']).name
            except LookupError as exc:
                raise ValueError('Unknown source encoding') from exc
            if codec not in _ALLOWED:
                raise ValueError('Unsupported legacy source encoding')
            parsed.append((_pattern(rule.get('pattern')), codec))
        return cls(tuple(parsed))

    @classmethod
    def load(cls, cache_root):
        path = Path(cache_root) / POLICY_PATH
        if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(Path(cache_root).resolve()):
            raise ValueError('Unsafe source encoding policy')
        if not path.exists():
            return cls()
        with path.open('rb') as stream:
            raw = stream.read(131073)
        if len(raw) > 131072:
            raise ValueError('Oversized source encoding policy')
        return cls.from_dict(json.loads(raw.decode('utf-8')))

    def profile(self, source_path):
        if not self.rules:
            return None
        path = canonical_path(source_path)
        codecs_found = {codec for pattern, codec in self.rules if pattern.fullmatch(path)}
        if len(codecs_found) > 1:
            raise ValueError('Conflicting source encoding rules; review matching patterns')
        return next(iter(codecs_found), None)


def decoding_options(source, context):
    if context is None:
        return {}
    policy = context.metadata_overrides.get('decoding_policy')
    if policy is None or not policy.rules:
        return {}
    path = Path(source.uri)
    root = Path(context.project_root).resolve()
    relative = path.resolve().relative_to(root).as_posix()
    if any(p.is_symlink() for p in (path, *path.parents) if p != root and p.is_relative_to(root)):
        raise ValueError('Source decoding does not follow symlinks')
    return {'source_path': relative, 'encoding_policy': policy}


def preview_policy(root, policy, *, family_resolver):
    """Report aggregate outcomes without echoing document text into diagnostics."""
    from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
    from pi_platform.core.ingest.records import read_text_with_provenance
    from pi_platform.ports.ingest.source_adapter import SourceAdapterError
    result = {'matched': 0, 'decoded': 0, 'failed': 0, 'unsupported': 0, 'encodings': {}}
    for entry in RepositorySourceDiscovery().discover(root).entries:
        if policy.profile(entry.path) is None:
            continue
        result['matched'] += 1
        if not supported_policy_target(entry.path, family_resolver(entry.path)):
            result['unsupported'] += 1
            result['failed'] += 1
            continue
        try:
            _, info = read_text_with_provenance(Path(root) / entry.path, source_path=entry.path, encoding_policy=policy)
        except SourceAdapterError:
            result['failed'] += 1
        else:
            result['decoded'] += 1
            codec = info['encoding']
            result['encodings'][codec] = result['encodings'].get(codec, 0) + 1
    return result


def supported_policy_target(path, family):
    return family in ('java_source', 'plain_text') and Path(path).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.jar'}

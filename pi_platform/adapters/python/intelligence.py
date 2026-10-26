"""Bounded, offline Python manifest and library evidence using only the stdlib."""
from __future__ import annotations

import ast
from dataclasses import replace
from email.parser import Parser
import io
from pathlib import Path, PurePosixPath
import re
import tokenize
import tomllib
import zipfile

from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.canonical.value_types import Entity, Evidence, KnowledgeState, Relation
from pi_platform.core.ingest.records import document_result, read_text
from pi_platform.ports.ingest.source_adapter import SourceAdapterError, SourceAdapterPort, SourceContentFamily

VERSION = 'python-static-1'
MAX_MEMBER_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
NAME = r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?'
REQUIREMENT = re.compile(rf'^({NAME})\s*(?:\[([^\]]*)\])?\s*(.*)$')
SPECIFIER = re.compile(r'(?:===|==|!=|~=|<=|>=|<|>)\s*[A-Za-z0-9.*+!_-]+(?:\s*,\s*(?:===|==|!=|~=|<=|>=|<|>)\s*[A-Za-z0-9.*+!_-]+)*\s*,?')


def normalize_name(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def python_family(path):
    """Shared inbox/repository dispatch. None means this adapter is not applicable."""
    p = Path(path)
    name = p.name.lower()
    if p.suffix.lower() in {'.py', '.pyi'}:
        return SourceContentFamily.PYTHON_SOURCE
    if p.suffix.lower() == '.whl':
        return SourceContentFamily.PYTHON_WHEEL
    if name == 'pyproject.toml' or (name.startswith('requirements') and p.suffix.lower() in {'.txt', '.in'}):
        return SourceContentFamily.PYTHON_MANIFEST
    return None


def requirement_record(text, scope='runtime'):
    """Project a declaration, retaining markers; never evaluate against the host."""
    text = text.strip()
    match = REQUIREMENT.fullmatch(text)
    if not match:
        raise ValueError('unsupported requirement')
    name, extras, tail = match.groups()
    if tail.startswith('@'):
        # URI semicolons are legal; a marker on a direct reference needs whitespace.
        parts = re.split(r'\s+;\s*', tail[1:].strip(), maxsplit=1)
        url, marker = parts[0], parts[1] if len(parts) > 1 else ''
        if not url or re.search(r'\s', url):
            raise ValueError('invalid direct reference')
        specifier = ''
    else:
        specifier, _, marker = tail.partition(';')
        specifier, marker = specifier.strip(), marker.strip()
        if specifier.startswith('(') and specifier.endswith(')'):
            specifier = specifier[1:-1].strip()
        if specifier and not SPECIFIER.fullmatch(specifier):
            raise ValueError('unsupported version specifier')
        url = ''
    extra_list = [normalize_name(e.strip()) for e in (extras or '').split(',') if e.strip()]
    if any(not re.fullmatch(NAME, e) for e in extra_list):
        raise ValueError('invalid extra')
    return {'ecosystem': 'python', 'name': normalize_name(name), 'requirement': text,
            'specifier': specifier, 'version': 'unresolved', 'extras': extra_list,
            'marker': marker, 'url': url, 'scope': scope, 'resolved': False,
            'spdx': None, 'licenseReview': 'required'}


def _result(source, rows, dependencies=(), apis=(), advisories=(), owner=None):
    advisory = '; '.join(advisories)
    rows = list(rows)
    if advisory:
        rows.append(('Analysis limits', 2, advisory, {'partial': True}))
    result = document_result(source, rows, 'python', VERSION, rationale=advisory or None)
    entities, relations, evidence = [], [], []

    def add(family, label, attrs, state=KnowledgeState.VERIFIED):
        eid = content_address({'source': source.id, 'hash': source.contentHash,
                               'family': family, 'label': label, 'attrs': attrs})
        ev = Evidence(state, VERSION, source.contentHash)
        meta = replace(result.document.metadata, extensions={**attrs, 'pi_evidence': {
            'knowledgeState': state.value, 'parserVersion': VERSION, 'sourceHash': source.contentHash}})
        entities.append(Entity(eid, family, label, metadata=meta, knowledgeState=state))
        evidence.append(ev)
        return eid

    module_id = add('Dependency' if owner else 'PythonModule',
                    owner['name'] if owner else Path(source.uri).name,
                    owner or {'ecosystem': 'python', 'partial': bool(advisories), 'advisories': list(advisories)})
    for dep in dependencies:
        eid = add('Dependency', dep['name'], dep, KnowledgeState.ASSUMPTION)
        for a, b, family in ((module_id, eid, 'DEPENDSON'), (eid, module_id, 'DECLARED_BY')):
            relations.append(Relation(a, b, family, evidence=(evidence[-1],), knowledgeState=KnowledgeState.ASSUMPTION))
    for family, name, attrs in apis:
        eid = add(family, name, attrs)
        relations.append(Relation(module_id, eid, 'CONTAINS', evidence=(evidence[-1],), knowledgeState=KnowledgeState.VERIFIED))
    return replace(result, entities=tuple(entities), relations=tuple(relations), evidence=tuple(evidence))


class PythonManifestAdapter(SourceAdapterPort):
    family = SourceContentFamily.PYTHON_MANIFEST

    def parse(self, source, context=None):
        text = read_text(source.uri)
        deps, advisories = [], []

        def collect(values, scope):
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise SourceAdapterError('Python dependencies must be an array of strings')
            for value in values:
                try:
                    deps.append(requirement_record(value, scope))
                except ValueError:
                    advisories.append(f'Unsupported declaration in {scope}: {value}')

        if Path(source.uri).name.lower() == 'pyproject.toml':
            try:
                data = tomllib.loads(text)
                project = data.get('project', {})
                collect(project.get('dependencies', []), 'runtime')
                for group, values in project.get('optional-dependencies', {}).items():
                    collect(values, 'extra:' + group)
                collect(data.get('build-system', {}).get('requires', []), 'build')
                for group, values in data.get('dependency-groups', {}).items():
                    collect([v for v in values if isinstance(v, str)], 'group:' + group)
                    if any(not isinstance(v, str) for v in values):
                        advisories.append(f'Group includes in {group} are not expanded')
                if project.get('dynamic'):
                    advisories.append('Dynamic project metadata is not evaluated: ' + ', '.join(project['dynamic']))
                if data.get('tool', {}).get('poetry'):
                    advisories.append('Legacy tool.poetry dependencies are not resolved; use project metadata or wheel METADATA')
            except (ValueError, TypeError, AttributeError) as exc:
                raise SourceAdapterError(f'invalid pyproject metadata: {exc}') from exc
        else:
            for line in re.sub(r'\\\r?\n', ' ', text).splitlines():
                line = re.split(r'\s+#', line, maxsplit=1)[0].strip()
                if not line or line.startswith('#'):
                    continue
                # Hashes attest downloads, not dependency identity. Never run pip options.
                line = re.sub(r'\s+--hash(?:=|\s+)\S+', '', line)
                if line.startswith(('-', '.', '/')):
                    advisories.append('Directive/local requirement not followed: ' + line)
                else:
                    collect([line], 'runtime')
        advisories.append('Declared requirements only; transitive closure and environment markers are unresolved')
        return _result(source, [(Path(source.uri).name, 1, text, {})], deps, advisories=advisories)


def source_api(text, module):
    tree = ast.parse(text)
    rows, apis = [(module, 1, text, {})], [('PythonModule', module, {'module': module, 'docstring': ast.get_docstring(tree) or ''})]

    def visit(body, prefix):
        for node in body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else ['.' * node.level + (node.module or '')]
                for name in names:
                    apis.append(('PythonImport', name, {'module': prefix, 'line': node.lineno, 'resolvedDistribution': None}))
            elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith('_'):
                qualified = prefix + '.' + node.name
                attrs = {'module': module, 'qualifiedName': qualified, 'line': node.lineno,
                         'docstring': ast.get_docstring(node) or ''}
                if isinstance(node, ast.ClassDef):
                    attrs['bases'] = [ast.unparse(b) for b in node.bases]
                    family = 'PythonClass'
                    visit(node.body, qualified)
                else:
                    attrs['signature'] = f'{node.name}({ast.unparse(node.args)})'
                    attrs['returns'] = ast.unparse(node.returns) if node.returns else None
                    attrs['async'] = isinstance(node, ast.AsyncFunctionDef)
                    family = 'PythonFunction'
                apis.append((family, qualified, attrs))
    visit(tree.body, module)
    return rows, apis


class PythonSourceAdapter(SourceAdapterPort):
    family = SourceContentFamily.PYTHON_SOURCE

    def parse(self, source, context=None):
        try:
            path = Path(source.uri)
            if path.stat().st_size > MAX_MEMBER_BYTES:
                raise ValueError('Python source exceeds 5 MiB')
            with tokenize.open(path) as stream:
                text = stream.read()
            relative = path.resolve().relative_to(Path(context.project_root).resolve()) if context else Path(path.name)
            module = '.'.join(relative.with_suffix('').parts)
            rows, apis = source_api(text, module)
            return _result(source, rows, apis=apis)
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            raise SourceAdapterError(f'cannot analyze Python source {source.uri}: {exc}') from exc


class PythonWheelAdapter(SourceAdapterPort):
    family = SourceContentFamily.PYTHON_WHEEL

    def parse(self, source, context=None):
        try:
            with zipfile.ZipFile(source.uri) as archive:
                infos = archive.infolist()
                if len(infos) > 10000 or sum(i.file_size for i in infos) > MAX_ARCHIVE_BYTES:
                    raise ValueError('wheel expanded size/member count exceeds limit')
                metadata = [i for i in infos if i.filename.endswith('.dist-info/METADATA')]
                if len(metadata) != 1:
                    raise ValueError('wheel must contain exactly one dist-info/METADATA')

                def read(info):
                    if info.file_size > MAX_MEMBER_BYTES:
                        raise ValueError('wheel analyzed member exceeds 5 MiB')
                    return archive.read(info)

                raw = read(metadata[0]).decode('utf-8')
                msg = Parser().parsestr(raw)
                if not msg.get('Name') or not msg.get('Version'):
                    raise ValueError('wheel metadata requires Name and Version')
                owner = {'ecosystem': 'python', 'name': normalize_name(msg['Name']),
                         'version': msg['Version'], 'resolved': True, 'type': 'wheel',
                         'spdx': msg.get('License-Expression'), 'licenseReview': 'required',
                         'requiresPython': msg.get('Requires-Python')}
                deps, advisories = [], ['Wheel metadata declarations; transitive closure and markers are unresolved']
                for value in msg.get_all('Requires-Dist', []):
                    try:
                        deps.append(requirement_record(value))
                    except ValueError:
                        advisories.append('Unsupported Requires-Dist: ' + value)
                rows, apis = [('Wheel metadata', 1, raw, owner)], []
                for info in sorted(infos, key=lambda i: i.filename):
                    path = PurePosixPath(info.filename)
                    if path.is_absolute() or '..' in path.parts or '\\' in info.filename:
                        raise ValueError('unsafe wheel member path')
                    if path.suffix not in {'.py', '.pyi'}:
                        continue
                    data = read(info)
                    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
                    member_rows, member_apis = source_api(data.decode(encoding), '.'.join(path.with_suffix('').parts))
                    rows.extend(member_rows)
                    apis.extend((family, label, {**attrs, 'archiveMember': info.filename}) for family, label, attrs in member_apis)
                return _result(source, rows, deps, apis, advisories, owner)
        except (OSError, ValueError, SyntaxError, UnicodeError, zipfile.BadZipFile, RuntimeError) as exc:
            raise SourceAdapterError(f'cannot analyze Python wheel {source.uri}: {exc}') from exc

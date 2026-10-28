"""Argument contracts shared by stdlib and SDK MCP transports."""
from copy import deepcopy

_TEXT = {'type': 'string'}
_VERSION = {'type': ['object', 'string', 'null'], 'description': 'Optional requested project version.'}
_SEARCH = {
    'text': {**_TEXT, 'description': 'Natural-language query or exact symbol to retrieve.'},
    'top_k': {'type': 'integer', 'minimum': 1, 'default': 10},
    'filters': {'type': ['object', 'null']},
    'project_version': _VERSION,
    'include_trace': {'type': 'boolean', 'default': False},
    'enable_reranking': {
        'type': ['boolean', 'null'],
        'description': (
            'Override the operator reranking policy for this query. '
            'Omit to use the configured policy (BM25-light reranking is '
            'active by default).'
        ),
    },
}
_CONTRACTS = {
    'search': (_SEARCH, ['text']),
    'retrieve_context': ({**_SEARCH, 'contextBudget': {'type': 'integer', 'minimum': 1, 'default': 2000}}, ['text']),
    'get_entity': ({'entity_id': _TEXT, 'project_version': _VERSION}, ['entity_id']),
    'get_component': ({'component_uri': _TEXT, 'project_version': _VERSION}, ['component_uri']),
    'get_requirement': ({'requirement_id': _TEXT, 'project_version': _VERSION}, ['requirement_id']),
    'get_spec': ({'spec_id': _TEXT, 'project_version': _VERSION}, ['spec_id']),
    'get_architecture': ({}, []),
    'get_dependency': ({k: _TEXT for k in ('group', 'artifact', 'version')}, ['group', 'artifact', 'version']),
    'dependency_tree': ({
        'ecosystem': {**_TEXT, 'enum': ['python', 'java', 'node'],
                      'description': 'The dependency ecosystem of the project.'},
        'package': {**_TEXT, 'description': 'Optional package name to start the traversal from.'},
        'environment': {**_TEXT, 'default': 'default',
                        'description': 'The environment to resolve for, e.g. a virtual environment name.'},
        'scopes': {'type': 'array', 'items': _TEXT,
                   'description': 'Optional dependency scopes to include, e.g. ["dev"].'},
        'max_depth': {'type': 'integer', 'minimum': 0, 'default': 5},
        'max_nodes': {'type': 'integer', 'minimum': 1, 'default': 100},
        'cursor': {**_TEXT, 'description': 'Continuation token of a truncated traversal.'},
    }, ['ecosystem']),
    'dependency_search': ({
        'ecosystem': {**_TEXT, 'enum': ['python', 'java', 'node']},
        'package_ref': {**_TEXT, 'description': 'The package whose symbols are searched.'},
        'query': {**_TEXT, 'description': 'The symbol name or fragment to look for.'},
        'limit': {'type': 'integer', 'minimum': 1, 'default': 20},
        'cursor': {**_TEXT},
    }, ['ecosystem', 'package_ref', 'query']),
    'dependency_read': ({
        'evidence_ref': {**_TEXT, 'description': 'The evidence reference of the code to read.'},
        'artifact': {**_TEXT, 'description': 'The acquired artifact path, when it is already known.'},
        'member': {**_TEXT, 'description': 'The member of the artifact to read.'},
        'symbol': {**_TEXT, 'description': 'Optional symbol to narrow the excerpt to.'},
        'start_line': {'type': 'integer', 'minimum': 1},
        'end_line': {'type': 'integer', 'minimum': 1},
        'max_bytes': {'type': 'integer', 'minimum': 1},
    }, []),
    'dependency_acquire': ({
        'ecosystem': {**_TEXT, 'enum': ['python', 'java', 'node']},
        'name': {**_TEXT, 'description': 'The exact package name.'},
        'version': {**_TEXT, 'description': 'The exact version.'},
        'source_id': {**_TEXT, 'description': 'The approved registry identity, e.g. "pypi".'},
    }, ['ecosystem', 'name', 'version', 'source_id']),
    'find_implementation': ({'requirement_id': _TEXT}, []),
    'trace_requirement': ({'requirement_id': _TEXT}, []),
    'find_references': ({'symbol': _TEXT}, []),
    'get_project_version': ({}, []),
    'get_conflicts': ({}, []),
    'get_stale_knowledge': ({}, []),
    'build_task_context': ({'goal': _TEXT, 'budget_tokens': {'type': 'integer', 'minimum': 1, 'default': 4000}, 'requirement_id': _TEXT}, ['goal']),
    'materialize_knowledge': ({'approval_id': _TEXT, 'repo_root': _TEXT, 'cache_root': _TEXT, 'change_ids': {'type':'array', 'items':_TEXT}}, ['approval_id']),
    'refresh_sources': ({'approval_id': _TEXT, 'repo_root': _TEXT}, ['approval_id']),
    'describe_capabilities': ({}, []),
    'get_retrieval_trace': ({'trace_id': _TEXT}, ['trace_id']),
    'wiki_list_pages': ({}, []),
    'wiki_read_page': ({
        'path': {**_TEXT, 'description': 'Wiki-relative page path, e.g. "architecture/overview.md".'},
        'include_body': {'type': 'boolean', 'default': True},
        'inputs': {
            'type': ['object', 'null'],
            'description': (
                'Optional current dependency state, keyed by package name, '
                'used to report which recorded evidence is stale.'
            ),
        },
    }, ['path']),
    'wiki_search': ({
        'query': {**_TEXT, 'description': 'Free-text query over the curated pages.'},
        'top_k': {'type': 'integer', 'minimum': 1, 'default': 8},
    }, ['query']),
    'wiki_write_page': ({
        'path': {**_TEXT, 'description': 'Wiki-relative page path, e.g. "architecture/overview.md".'},
        'title': {**_TEXT, 'description': 'Human-readable page title.'},
        'body': {**_TEXT, 'description': 'The Markdown body of the page.'},
        'type': {
            'type': 'string', 'default': 'Concept',
            'enum': [
                'Concept', 'Architecture', 'Module', 'Interface', 'Process',
                'Decision', 'Requirement', 'Glossary', 'Domain', 'Invariant',
            ],
            'description': 'OKF concept type of the page.',
        },
        'summary': {'type': 'string', 'default': ''},
        'author': {'type': 'string', 'default': 'calling-llm'},
        'source': {'type': 'string', 'default': ''},
        'dry_run': {'type': 'boolean', 'default': False},
        'expected_revision': {
            'type': ['string', 'null'],
            'description': (
                'The revision the caller read. A page that changed in the '
                'meantime produces a conflict instead of an overwrite.'
            ),
        },
        'dependency_notes': {
            'type': ['array', 'null'],
            'items': {'type': 'object'},
            'description': (
                'The provenance of the research the page explains: package, '
                'version, artifact hash, evidence references and tool version.'
            ),
        },
    }, ['path', 'title', 'body']),
    'wiki_validate': ({}, []),
}


def tool_definition(name):
    properties, required = _CONTRACTS[name.removeprefix('project.')]
    return {'name': name, 'description': name.replace('_', ' '),
            'inputSchema': {'type': 'object', 'properties': deepcopy(properties),
                            'required': list(required), 'additionalProperties': False}}

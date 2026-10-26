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
    }, ['path', 'title', 'body']),
    'wiki_validate': ({}, []),
}


def tool_definition(name):
    properties, required = _CONTRACTS[name.removeprefix('project.')]
    return {'name': name, 'description': name.replace('_', ' '),
            'inputSchema': {'type': 'object', 'properties': deepcopy(properties),
                            'required': list(required), 'additionalProperties': False}}

"""Configure the same private chat connection used by the UI, before serving."""
import json
import os
from pathlib import Path
import sys

from pi_platform.adapters.orchestration.chat_connection import ChatConnection, ChatConnectionError


def register_chat_parser(subparsers):
    parser = subparsers.add_parser('chat', help='configure/test the optional UI chat model without starting services')
    commands = parser.add_subparsers(dest='chat_command', required=True)
    for name in ('configure', 'status', 'test', 'disable'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--target', type=Path, default=Path('.'))
        if name == 'configure':
            cmd.add_argument('--from-env', action='store_true', help='read LLM_PROVIDER, LLM_URL, LLM_MODEL, LLM_API_KEY, LLM_SHARE_CONTEXT, LLM_ENABLED')
            cmd.add_argument('--provider', choices=('openai', 'anthropic'))
            cmd.add_argument('--base-url')
            cmd.add_argument('--model')
            cmd.add_argument('--share-context', action='store_const', const=True, default=None)
            cmd.add_argument('--api-key-stdin', action='store_true', help='read the provider key from stdin, never from an argument')
            enabled = cmd.add_mutually_exclusive_group()
            enabled.add_argument('--enable', dest='enabled', action='store_true', default=None)
            enabled.add_argument('--disable', dest='enabled', action='store_false')


def _boolean(name, value):
    if value.lower() in {'1', 'true', 'yes'}:
        return True
    if value.lower() in {'0', 'false', 'no'}:
        return False
    raise ValueError(f'{name} must be 1/0 or true/false')


def run_chat_command(args):
    connection = ChatConnection(args.target.resolve() / '.project-intelligence-cache')
    try:
        if args.chat_command == 'configure':
            patch = {}
            if args.from_env:
                fields = {'LLM_PROVIDER':'provider', 'LLM_URL':'base_url', 'LLM_MODEL':'model',
                          'LLM_API_KEY':'api_key', 'LLM_SHARE_CONTEXT':'share_context', 'LLM_ENABLED':'enabled'}
                for name, field in fields.items():
                    value = os.environ.get(name, '')
                    if value:
                        patch[field] = _boolean(name, value) if field in {'enabled', 'share_context'} else value
            for field in ('provider', 'base_url', 'model', 'share_context', 'enabled'):
                value = getattr(args, field, None)
                if value is not None:
                    patch[field] = value
            if args.api_key_stdin:
                key = sys.stdin.read(16385).rstrip('\r\n')
                if len(key) > 16384:
                    raise ValueError('Provider key exceeds the size limit')
                patch['api_key'] = key
            patch.setdefault('enabled', True)
            result = connection.save(patch)
        elif args.chat_command == 'disable':
            result = connection.save({'enabled': False})
        elif args.chat_command == 'test':
            result = connection.test()
        else:
            result = connection.public_settings()
        print(json.dumps(result, indent=2))
        return 1 if result.get('ok') is False else 0
    except (ValueError, ChatConnectionError, OSError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 2

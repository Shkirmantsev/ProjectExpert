"""Exercise real connectable background MCP lifecycle on Linux and Windows."""
import asyncio
import datetime as dt
import importlib.util
from pathlib import Path
import socket
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / 'scripts'))
from project_mcp import Lifecycle


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'MCP dependency not installed')
class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_stdio_launcher_has_no_protocol_banner(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as raw:
            command = StdioServerParameters(command=sys.executable,
                args=[str(REPO / 'harness.py'), 'mcp-stdio'], cwd=raw)
            async with stdio_client(command) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=dt.timedelta(seconds=10)) as client:
                    await client.initialize()
                    self.assertIn('kb_search', [tool.name for tool in (await client.list_tools()).tools])

    async def test_connectable_start_duplicate_collision_stop_and_clean(self):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        with tempfile.TemporaryDirectory(prefix='MCP lifecycle ') as raw:
            root = Path(raw) / 'repo with spaces'
            wiki = root / '.ai/wiki'
            wiki.mkdir(parents=True)
            (wiki / 'INDEX.md').write_text('---\nid: wiki.index\n---\n# Index\nlifecycle-canary\n', encoding='utf-8')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            lifecycle = Lifecycle(Path(raw) / 'state')
            collision = Lifecycle(Path(raw) / 'collision')
            try:
                self.assertEqual(await asyncio.to_thread(lifecycle.start, root, port, Path(sys.executable)), 0)
                state = lifecycle.read()
                self.assertEqual(lifecycle.status(), 0)
                self.assertEqual(await asyncio.to_thread(lifecycle.start, root, port, Path(sys.executable)), 0)
                self.assertEqual(lifecycle.read()['workerPid'], state['workerPid'])
                self.assertEqual(lifecycle.clean(), 1)
                async with streamable_http_client(f'http://127.0.0.1:{port}/mcp') as (read, write, _):
                    async with ClientSession(read, write, read_timeout_seconds=dt.timedelta(seconds=10)) as client:
                        await client.initialize()
                        tools = await client.list_tools()
                        self.assertIn('kb_search', [tool.name for tool in tools.tools])
                        result = await client.call_tool('kb_search', {'query': 'lifecycle'})
                        self.assertFalse(result.isError)
                        self.assertIn('wiki.index', str(result))
                # Another process on the same port must neither satisfy readiness nor be stopped.
                self.assertEqual(await asyncio.to_thread(collision.start, root, port, Path(sys.executable)), 1)
                self.assertEqual(await asyncio.to_thread(collision.stop), 0)
                self.assertEqual(lifecycle.status(), 0)
                self.assertEqual(await asyncio.to_thread(lifecycle.stop), 0)
                self.assertEqual(lifecycle.status(), 1)
                self.assertEqual(await asyncio.to_thread(lifecycle.stop), 0)
                lifecycle.logs()
                self.assertEqual(lifecycle.clean(), 0)
                self.assertFalse(lifecycle.state_file.exists())
                self.assertFalse(lifecycle.log_file.exists())
                self.assertTrue((wiki / 'INDEX.md').is_file())
            finally:
                await asyncio.to_thread(collision.stop)
                await asyncio.to_thread(lifecycle.stop)

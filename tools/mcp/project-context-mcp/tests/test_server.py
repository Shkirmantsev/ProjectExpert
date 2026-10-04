"""Exercise the installed MCP over stdio, including an unrelated launch directory."""
import importlib.util
import datetime as dt
from pathlib import Path
import sys
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'MCP dependency not installed')
class ServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_round_trip_and_change_boundary(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'repo'
            wiki = root / '.ai/wiki'
            wiki.mkdir(parents=True)
            (wiki / 'INDEX.md').write_text('---\nid: wiki.index\n---\n# Index\nreservation-canary\n')
            specs = root / 'openspec/specs'
            specs.mkdir(parents=True)
            (specs / 'current.md').write_text('Current requirements')
            change = root / 'openspec/changes/demo'
            change.mkdir(parents=True)
            (change / 'proposal.md').write_text('Proposed requirements')
            server = StdioServerParameters(
                command=sys.executable,
                args=['-m', 'project_context_mcp.server', '--root', str(root)],
                cwd=d,
            )
            async with stdio_client(server) as (read, write):
                async with ClientSession(
                    read,
                    write,
                    read_timeout_seconds=dt.timedelta(seconds=10),
                ) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    self.assertIn('kb_search', [t.name for t in tools.tools])
                    result = await client.call_tool('kb_search', {'query': 'reservation'})
                    self.assertFalse(result.isError)
                    self.assertIn('wiki.index', str(result))
                    result = await client.call_tool('kb_get', {'id': 'wiki.index'})
                    self.assertIn('reservation-canary', str(result))
                    result = await client.call_tool('spec_context', {'change_id': '../specs'})
                    self.assertIn('invalid change id', str(result))
                    self.assertNotIn('Current requirements', str(result))
                    result = await client.call_tool('spec_context', {'change_id': 'demo'})
                    self.assertIn('Proposed requirements', str(result))

"""MCP server ``build_default_tool_context`` factory tests.

The v0.8 refinement (``improve-ingestion-retrieval-local-models``,
Change Package I / MAJOR-2) ships the ``PI_MCP_DEBUG=1`` activation
path documented in the agent skill and the MCP server error
messages. :func:`pi_platform.mcp.context.build_default_tool_context`
is the production factory for the :class:`ToolContext` and honours
the env var.

The tests assert:

* the env-var name is stable;
* the factory returns a debug-off / no-trace-store context by
  default;
* the factory returns a debug-on / in-memory trace store when the
  env var is set;
* the factory accepts an explicit ``debug_mode`` override that
  wins over the env var;
* the factory returns a context whose ``§36`` tool inventory is
  unchanged (the public surface stays intact in production).
"""

from __future__ import annotations

import os
import unittest

from pi_platform.adapters.retrieval.in_memory_trace_store import (
    InMemoryRetrievalTraceStore,
)
from pi_platform.mcp.context import (
    DEBUG_ENV_VAR,
    TRUTHY_DEBUG_VALUES,
    build_default_tool_context,
    default_debug_mode,
)
from pi_platform.mcp.server import (
    McpServer,
    SECTION_36_TOOLS,
)


__all__ = ["McpContextFactoryTests"]


class McpContextFactoryTests(unittest.TestCase):

    def setUp(self) -> None:
        # Snapshot the env so the test does not leak PI_MCP_DEBUG
        # to other tests / the host shell.
        self._saved = os.environ.get(DEBUG_ENV_VAR)
        os.environ.pop(DEBUG_ENV_VAR, None)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(DEBUG_ENV_VAR, None)
        else:
            os.environ[DEBUG_ENV_VAR] = self._saved

    def test_debug_env_var_is_stable(self) -> None:
        self.assertEqual(DEBUG_ENV_VAR, "PI_MCP_DEBUG")
        # The truthy value set is frozen so the documentation,
        # error messages and tests cannot drift apart.
        self.assertIn("1", TRUTHY_DEBUG_VALUES)
        self.assertIn("true", TRUTHY_DEBUG_VALUES)

    def test_default_debug_mode_is_off(self) -> None:
        self.assertFalse(default_debug_mode({}))
        self.assertFalse(default_debug_mode())

    def test_default_debug_mode_accepts_truthy_values(self) -> None:
        for value in ("1", "true", "TRUE", "yes", "on"):
            self.assertTrue(
                default_debug_mode({DEBUG_ENV_VAR: value}),
                f"truthy value {value!r} not detected",
            )

    def test_default_debug_mode_rejects_other_values(self) -> None:
        for value in ("0", "false", "no", "off", ""):
            self.assertFalse(
                default_debug_mode({DEBUG_ENV_VAR: value}),
                f"non-truthy value {value!r} not detected",
            )

    def test_factory_default_is_production_safe(self) -> None:
        ctx = build_default_tool_context()
        self.assertFalse(ctx.debug_mode)
        self.assertIsNone(ctx.trace_store)

    def test_factory_enables_debug_mode_via_env_var(self) -> None:
        os.environ[DEBUG_ENV_VAR] = "1"
        ctx = build_default_tool_context()
        self.assertTrue(ctx.debug_mode)
        self.assertIsInstance(ctx.trace_store, InMemoryRetrievalTraceStore)

    def test_factory_enables_debug_mode_via_explicit_flag(self) -> None:
        ctx = build_default_tool_context(debug_mode=True)
        self.assertTrue(ctx.debug_mode)
        self.assertIsInstance(ctx.trace_store, InMemoryRetrievalTraceStore)

    def test_factory_off_when_explicit_off_and_env_on(self) -> None:
        # The explicit flag is a higher-priority override.
        os.environ[DEBUG_ENV_VAR] = "1"
        ctx = build_default_tool_context(debug_mode=False)
        self.assertFalse(ctx.debug_mode)
        self.assertIsNone(ctx.trace_store)

    def test_factory_accepts_custom_trace_store(self) -> None:
        custom = InMemoryRetrievalTraceStore(capacity=4)
        ctx = build_default_tool_context(
            debug_mode=True, trace_store=custom,
        )
        self.assertIs(ctx.trace_store, custom)

    def test_factory_section_36_inventory_unchanged(self) -> None:
        # The factory must not introduce new §36 tools; the
        # public surface stays the same. The debug-only tool
        # is hidden when debug mode is off.
        ctx_off = build_default_tool_context()
        server_off = McpServer(context=ctx_off)
        for name in SECTION_36_TOOLS:
            self.assertIn(name, server_off.tool_names)
        self.assertNotIn(
            "project.get_retrieval_trace", server_off.tool_names,
        )

        ctx_on = build_default_tool_context(debug_mode=True)
        server_on = McpServer(context=ctx_on)
        for name in SECTION_36_TOOLS:
            self.assertIn(name, server_on.tool_names)
        self.assertIn(
            "project.get_retrieval_trace", server_on.tool_names,
        )

    def test_factory_returns_default_capability_discovery(self) -> None:
        ctx = build_default_tool_context()
        descriptor = ctx.capability_discovery.describe()
        self.assertIsNotNone(descriptor)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
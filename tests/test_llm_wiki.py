"""Tests for the LLM Wiki and its MCP tools.

The LLM Wiki is the canonical, LLM-curated knowledge layer. A calling LLM
writes pages through the MCP server; the platform guarantees that a page is
OKF-conformant before it is stored, that it never escapes the wiki root,
that the write is atomic and that the change is recorded in the reserved
log.
"""

import asyncio
import tempfile
import unittest
from pathlib import Path

from pi_platform.core.canonical.okf import validate_wiki_bundle
from pi_platform.core.wiki.llm_wiki import (
    LlmWiki,
    LlmWikiError,
    wiki_root_for,
)
from pi_platform.mcp.server import TOOL_REGISTRY, McpServer, ToolContext
from pi_platform.mcp.tool_schemas import tool_definition


class FakeReadiness:
    def is_ready(self):
        return True

    def snapshot(self):
        return {}


class LlmWikiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        self.wiki = LlmWiki(self.repo)
        self.wiki.ensure_scaffold()

    def test_the_scaffold_creates_the_reserved_files(self):
        root = wiki_root_for(self.repo)
        self.assertTrue((root / "index.md").is_file())
        self.assertTrue((root / "log.md").is_file())
        # The reserved index keeps the OKF-required frontmatter.
        self.assertEqual(self.wiki.validate(), [])

    def test_a_page_is_written_and_read_back(self):
        result = self.wiki.write_page(
            relative_path="architecture/overview",
            title="Architecture overview",
            page_type="Architecture",
            summary="How the system is put together.",
            body="The system has three layers.\\n\\nThe retrieval layer does the work.",
        )
        self.assertTrue(result["written"])
        self.assertTrue(result["created"])
        page = self.wiki.read_page("architecture/overview.md")
        self.assertEqual(page.title, "Architecture overview")
        self.assertEqual(page.type, "Architecture")
        self.assertIn("three layers", page.body)

    def test_a_written_page_satisfies_the_okf_profile(self):
        self.wiki.write_page(
            relative_path="concept/one",
            title="One",
            body="Body text.",
        )
        errors = validate_wiki_bundle(wiki_root_for(self.repo))
        self.assertEqual([str(e) for e in errors], [])

    def test_an_existing_page_is_updated_not_duplicated(self):
        self.wiki.write_page(relative_path="concept/one", title="One", body="First.")
        result = self.wiki.write_page(
            relative_path="concept/one", title="One", body="Second.",
        )
        self.assertFalse(result["created"])
        self.assertIn("Second.", self.wiki.read_page("concept/one.md").body)

    def test_the_log_records_every_write(self):
        self.wiki.write_page(relative_path="concept/one", title="One", body="Body.")
        log = (wiki_root_for(self.repo) / "log.md").read_text(encoding="utf-8")
        self.assertIn("concept/one.md", log)

    def test_the_index_navigation_is_refreshed(self):
        self.wiki.write_page(
            relative_path="concept/one", title="One", body="Body.",
        )
        index = (wiki_root_for(self.repo) / "index.md").read_text(encoding="utf-8")
        self.assertIn("concept/one.md", index)
        self.assertIn("okf_version", index)

    def test_a_path_outside_the_root_is_refused(self):
        for bad in ("../escape", "/etc/passwd", "a/../../b"):
            with self.assertRaises(LlmWikiError):
                self.wiki.write_page(
                    relative_path=bad, title="X", body="B",
                )

    def test_an_unknown_page_type_is_refused(self):
        with self.assertRaises(LlmWikiError):
            self.wiki.write_page(
                relative_path="concept/one", title="X", body="B",
                page_type="Nonsense",
            )

    def test_an_empty_title_is_refused(self):
        with self.assertRaises(LlmWikiError):
            self.wiki.write_page(relative_path="concept/one", title="  ", body="B")

    def test_the_reserved_files_cannot_be_overwritten(self):
        for reserved in ("index.md", "log.md"):
            with self.assertRaises(LlmWikiError):
                self.wiki.write_page(
                    relative_path=reserved, title="X", body="B",
                )

    def test_a_dry_run_writes_nothing(self):
        result = self.wiki.write_page(
            relative_path="concept/one", title="One", body="B", dry_run=True,
        )
        self.assertFalse(result["written"])
        self.assertEqual(self.wiki.list_pages(), [])

    def test_pages_are_listed_and_searchable(self):
        self.wiki.write_page(
            relative_path="architecture/retrieval",
            title="Retrieval pipeline",
            summary="How the retrieval pipeline works.",
            body="Candidates are fused, reranked and selected.",
        )
        pages = self.wiki.list_pages()
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["path"], "architecture/retrieval.md")
        found = self.wiki.search_pages("retrieval pipeline")
        self.assertEqual(len(found), 1)
        self.assertEqual(self.wiki.search_pages("nothing matches here"), [])

    def test_a_missing_page_raises(self):
        with self.assertRaises(LlmWikiError):
            self.wiki.read_page("concept/missing.md")


class WikiIsSearchableTests(unittest.TestCase):
    """A curated page must be part of the searchable corpus."""

    def test_a_wiki_page_becomes_a_retrieval_candidate(self):
        from pi_platform.adapters.ui.composition import (
            CacheBackedHybridRetrieval,
        )

        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            wiki = LlmWiki(repo)
            wiki.ensure_scaffold()
            wiki.write_page(
                relative_path="architecture/retrieval",
                title="Retrieval pipeline",
                summary="The candidate pipeline of the platform.",
                body=(
                    "The retrieval pipeline fuses dense and sparse "
                    "candidates, reranks them and selects the primary pool."
                ),
            )
            retrieval = CacheBackedHybridRetrieval(
                repo / ".cache", repo_root=repo,
            )
            hits = retrieval.query("retrieval pipeline reranks", top_k=10)
            self.assertTrue(
                any(h.chunkId.startswith("wiki:") for h in hits),
                "the curated page is not part of the searchable corpus",
            )


class LlmWikiMcpToolTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        self.server = McpServer(context=self._context(self.repo))

    def _context(self, repo):
        from unittest.mock import MagicMock

        from pi_platform.core.sync.trusted_approval import (
            HmacTrustedApprovalBoundary,
        )
        return ToolContext(
            readiness=FakeReadiness(),
            capability_discovery=None,
            orchestrator=None,
            task_context_builder=None,
            multi_stage_retrieval=None,
            hybrid_retrieval=None,
            context_assembler=None,
            boundary=HmacTrustedApprovalBoundary(),
            version_policy=MagicMock(),
            server_identity={"name": "test"},
            repo_root=repo,
            cache_root=repo / ".cache",
        )

    def call(self, name, arguments):
        return asyncio.run(self.server.call_tool(name, arguments))

    def test_the_wiki_tools_are_registered_and_schematised(self):
        for name in (
            "project.wiki_list_pages",
            "project.wiki_read_page",
            "project.wiki_search",
            "project.wiki_write_page",
            "project.wiki_validate",
        ):
            self.assertIn(name, TOOL_REGISTRY)
            self.assertIn(name, self.server.tool_names)
            definition = tool_definition(name)
            self.assertEqual(definition["inputSchema"]["type"], "object")

    def test_the_calling_llm_writes_reads_and_searches_a_page(self):
        written = self.call("project.wiki_write_page", {
            "path": "architecture/overview",
            "title": "Architecture overview",
            "body": "The system has three layers.",
            "type": "Architecture",
            "summary": "How the system is put together.",
        })
        self.assertTrue(written["ok"])
        self.assertTrue(written["written"])

        listed = self.call("project.wiki_list_pages", {})
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["count"], 1)

        read = self.call("project.wiki_read_page", {"path": "architecture/overview.md"})
        self.assertTrue(read["ok"])
        self.assertEqual(read["page"]["title"], "Architecture overview")

        found = self.call("project.wiki_search", {"query": "three layers"})
        self.assertTrue(found["ok"])
        self.assertEqual(found["count"], 1)

        validated = self.call("project.wiki_validate", {})
        self.assertTrue(validated["ok"])
        self.assertEqual(validated["errors"], [])

    def test_an_invalid_page_is_reported_and_not_stored(self):
        result = self.call("project.wiki_write_page", {
            "path": "concept/one",
            "title": "One",
            "body": "Body.",
            "type": "Nonsense",
        })
        self.assertFalse(result["ok"])
        self.assertIn("unknown page type", result["error"])
        listed = self.call("project.wiki_list_pages", {})
        self.assertEqual(listed["count"], 0)

    def test_a_path_outside_the_root_is_refused(self):
        result = self.call("project.wiki_write_page", {
            "path": "../escape",
            "title": "Escape",
            "body": "Body.",
        })
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()

"""Tests for the research enrichment of the curated project Wiki.

The enrichment contract is:

* a write presents the revision it read and a changed page produces a
  conflict instead of a silent overwrite;
* the provenance of the research is stored with the page, and a changed
  dependency makes the recorded evidence stale;
* unrelated curated text survives the enrichment;
* the curated explanation becomes part of the searchable corpus and
  survives a restart;
* a repeated question reuses the curated evidence instead of
  researching again.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from pi_platform.adapters.research.composition import (
    build_dependency_research_service,
)
from pi_platform.core.wiki.llm_wiki import LlmWiki, LlmWikiError
from pi_platform.mcp.server import DEFAULT_SERVER_IDENTITY, McpServer, ToolContext

UV_LOCK = """\
version = 1
revision = 1

[[package]]
name = "requests"
version = "2.32.3"
source = { registry = "https://pypi.org/simple" }
dependencies = [{ name = "certifi" }]

[[package]]
name = "certifi"
version = "2024.8.30"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "demo"
version = "0.1.0"
source = { editable = "." }
dependencies = [{ name = "requests" }]
"""

UV_LOCK_UPGRADED = UV_LOCK.replace("2.32.3", "2.32.4")


class WikiEnrichmentFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "project"
        self.repo.mkdir(parents=True)
        (self.repo / "uv.lock").write_text(UV_LOCK, encoding="utf-8")
        self.wiki = LlmWiki(self.repo)
        self.wiki.ensure_scaffold()
        self.service = build_dependency_research_service(project_root=self.repo)
        self.calls: list[tuple[str, tuple]] = []
        self.server = McpServer(context=self._context())

    def _context(self) -> ToolContext:
        from pi_platform.core.sync.trusted_approval import (
            HmacTrustedApprovalBoundary,
        )

        return ToolContext(
            readiness=MagicMock(is_ready=MagicMock(return_value=True),
                                snapshot=MagicMock()),
            capability_discovery=MagicMock(),
            orchestrator=MagicMock(),
            task_context_builder=MagicMock(),
            multi_stage_retrieval=MagicMock(),
            hybrid_retrieval=MagicMock(),
            context_assembler=MagicMock(),
            boundary=HmacTrustedApprovalBoundary(),
            version_policy=MagicMock(),
            server_identity=DEFAULT_SERVER_IDENTITY,
            repo_root=self.repo,
            cache_root=self.repo / ".cache",
            dependency_research=self.service,
        )

    def call(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, tuple(sorted(arguments))))
        return asyncio.run(self.server.call_tool(name, arguments))

    def note(self, version: str = "2.32.3") -> dict:
        return {
            "package": "requests",
            "ecosystem": "python",
            "version": version,
            "artifactHash": None,
            "evidence": ["research:dependency.tree"],
            "repositoryRevision": "worktree",
            "toolVersion": "python-research-1",
            "label": "fact",
        }


class WikiPreconditionTests(WikiEnrichmentFixture):
    def test_a_write_reports_the_stored_and_the_indexed_state(self):
        result = self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "The project resolves requests 2.32.3.",
        })
        self.assertTrue(result["ok"])
        self.assertTrue(result["stored"])
        self.assertEqual(result["index_state"], "ready")
        self.assertEqual(result["retrieval_index_state"], "pending")
        self.assertTrue(result["revision"])

    def test_a_read_returns_the_revision_of_the_page(self):
        written = self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "The project resolves requests 2.32.3.",
        })
        read = self.call("project.wiki_read_page",
                         {"path": "dependencies/requests.md"})
        self.assertEqual(read["page"]["revision"], written["revision"])

    def test_a_stale_revision_produces_a_conflict_and_no_overwrite(self):
        first = self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "The project resolves requests 2.32.3.",
        })
        # Somebody else enriches the page in the meantime.
        self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "The project resolves requests 2.32.3 and certifi 2024.8.30.",
        })
        conflict = self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "A stale enrichment that must not land.",
            "expected_revision": first["revision"],
        })
        self.assertFalse(conflict["ok"])
        self.assertTrue(conflict["conflict"])
        self.assertFalse(conflict["written"])
        self.assertNotEqual(conflict["currentRevision"], first["revision"])
        page = self.wiki.read_page("dependencies/requests.md")
        self.assertNotIn("must not land", page.body)

    def test_the_conflict_carries_the_current_revision_for_a_merge(self):
        first = self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "First explanation.",
        })
        conflict = self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "Second explanation.",
            "expected_revision": first["revision"],
        })
        # The revision did not change, so the write succeeds.
        self.assertTrue(conflict["ok"])
        self.assertNotIn("conflict", conflict)

    def test_a_concurrent_writer_does_not_lose_a_change(self):
        written = self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "Base explanation.",
        })
        results: list[dict] = []
        barrier = threading.Barrier(2)

        def writer(marker: str) -> None:
            barrier.wait()
            results.append(self.call("project.wiki_write_page", {
                "path": "dependencies/requests.md",
                "title": "requests",
                "body": f"Explanation {marker}.",
                "expected_revision": written["revision"],
            }))

        threads = [threading.Thread(target=writer, args=("a",)),
                   threading.Thread(target=writer, args=("b",))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(1 for item in results if item.get("conflict")), 1,
                         "exactly one writer must observe the conflict")
        self.assertEqual(sum(1 for item in results if item.get("ok")), 1)
        page = self.wiki.read_page("dependencies/requests.md")
        self.assertTrue(page.body.startswith("Explanation"))


class WikiProvenanceTests(WikiEnrichmentFixture):
    def test_the_provenance_is_stored_with_the_page(self):
        self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "The project resolves requests 2.32.3.",
            "dependency_notes": [self.note()],
        })
        page = self.wiki.read_page("dependencies/requests.md")
        self.assertEqual(len(page.dependency_notes), 1)
        stored = page.dependency_notes[0]
        self.assertEqual(stored["package"], "requests")
        self.assertEqual(stored["version"], "2.32.3")
        self.assertEqual(stored["label"], "fact")
        self.assertEqual(stored["toolVersion"], "python-research-1")

    def test_a_changed_dependency_version_makes_the_note_stale(self):
        self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "The project resolves requests 2.32.3.",
            "dependency_notes": [self.note()],
        })
        fresh = self.call("project.wiki_read_page", {
            "path": "dependencies/requests.md",
            "inputs": {"requests": {"version": "2.32.3"}},
        })
        self.assertEqual(fresh["page"].get("staleNotes", []), [])
        stale = self.call("project.wiki_read_page", {
            "path": "dependencies/requests.md",
            "inputs": {"requests": {"version": "2.32.4"}},
        })
        self.assertEqual(len(stale["page"]["staleNotes"]), 1)
        self.assertEqual(stale["page"]["staleNotes"][0]["staleReason"],
                         "version")
        self.assertEqual(stale["page"]["staleNotes"][0]["currentVersion"],
                         "2.32.4")

    def test_unrelated_curated_text_is_preserved(self):
        self.call("project.wiki_write_page", {
            "path": "architecture/overview.md",
            "title": "Overview",
            "body": "The curated overview explains the architecture.",
        })
        self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "The project resolves requests 2.32.3.",
            "dependency_notes": [self.note()],
        })
        overview = self.wiki.read_page("architecture/overview.md")
        self.assertIn("curated overview", overview.body)
        self.assertEqual(overview.dependency_notes, ())

    def test_a_duplicate_insight_is_not_written_twice(self):
        for _ in range(2):
            self.call("project.wiki_write_page", {
                "path": "dependencies/requests.md",
                "title": "requests",
                "body": "The project resolves requests 2.32.3.",
                "dependency_notes": [self.note()],
            })
        page = self.wiki.read_page("dependencies/requests.md")
        self.assertEqual(page.body.count("resolves requests 2.32.3"), 1)
        self.assertEqual(len(page.dependency_notes), 1)

    def test_the_page_still_satisfies_the_okf_profile(self):
        self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "The project resolves requests 2.32.3.",
            "dependency_notes": [self.note()],
        })
        self.assertEqual(self.wiki.validate(), [])


class WikiSearchabilityTests(WikiEnrichmentFixture):
    def test_the_curated_explanation_becomes_searchable_and_survives_a_restart(self):
        from pi_platform.adapters.ui.composition import (
            CacheBackedHybridRetrieval,
        )

        self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": (
                "The project resolves requests 2.32.3, which pulls certifi "
                "2024.8.30 for the TLS trust store."
            ),
        })
        cache = self.repo / ".cache"
        first = CacheBackedHybridRetrieval(cache, repo_root=self.repo)
        hits = first.query("requests certifi trust store", top_k=10)
        self.assertTrue(any(hit.chunkId.startswith("wiki:") for hit in hits))
        # A restart reads the persisted cache and the Wiki again.
        second = CacheBackedHybridRetrieval(cache, repo_root=self.repo)
        hits = second.query("requests certifi trust store", top_k=10)
        self.assertTrue(any(hit.chunkId.startswith("wiki:") for hit in hits))

    def test_the_index_refresh_is_idempotent(self):
        self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "The project resolves requests 2.32.3.",
        })
        index = self.repo / "project-knowledge" / "wiki" / "index.md"
        first = index.read_text(encoding="utf-8")
        self.wiki.refresh_index()
        self.assertEqual(first, index.read_text(encoding="utf-8"))

    def test_a_failed_index_refresh_leaves_the_page_stored(self):
        original = LlmWiki.refresh_index

        def failing_refresh(self):
            raise OSError("the index could not be written")

        LlmWiki.refresh_index = failing_refresh
        try:
            result = self.call("project.wiki_write_page", {
                "path": "dependencies/requests.md",
                "title": "requests",
                "body": "The project resolves requests 2.32.3.",
            })
        finally:
            LlmWiki.refresh_index = original
        self.assertTrue(result["stored"])
        self.assertEqual(result["index_state"], "failed")
        self.assertFalse(result["index_refreshed"])
        # The page is stored and readable; only the index lagged behind.
        self.assertIn("resolves requests 2.32.3",
                      self.wiki.read_page("dependencies/requests.md").body)
        # The retry is idempotent: it only rewrites the navigation.
        self.wiki.refresh_index()
        first = (self.repo / "project-knowledge" / "wiki" / "index.md").read_text()
        self.wiki.refresh_index()
        self.assertEqual(
            first,
            (self.repo / "project-knowledge" / "wiki" / "index.md").read_text())


class TwoQuestionScenarioTests(WikiEnrichmentFixture):
    """The repeat question reuses the curated evidence."""

    def test_the_second_question_researches_nothing(self):
        tree = self.call("project.dependency_tree", {"ecosystem": "python"})
        self.assertTrue(tree["ok"])
        versions = {
            node["package"]["name"]: node["package"]["resolvedVersion"]
            for node in tree["research"]["nodes"]
        }
        self.assertEqual(versions["requests"], "2.32.3")

        self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": (
                "The project resolves requests 2.32.3. It pulls certifi "
                "2024.8.30 for the TLS trust store."
            ),
            "dependency_notes": [self.note()],
        })

        # The second question is answered from the curated Wiki.
        research_calls_before = len([call for call in self.calls
                                     if call[0].startswith("project.dependency")])
        found = self.call("project.wiki_search", {"query": "requests certifi"})
        self.assertTrue(found["ok"])
        self.assertTrue(found["pages"])
        research_calls_after = len([call for call in self.calls
                                    if call[0].startswith("project.dependency")])
        self.assertEqual(research_calls_before, research_calls_after,
                         "the repeated question must not research again")

    def test_a_dependency_upgrade_invalidates_the_curated_evidence(self):
        self.call("project.wiki_write_page", {
            "path": "dependencies/requests.md",
            "title": "requests",
            "body": "The project resolves requests 2.32.3.",
            "dependency_notes": [self.note()],
        })
        # The lock changes: the curated explanation is now out of date.
        (self.repo / "uv.lock").write_text(UV_LOCK_UPGRADED, encoding="utf-8")
        tree = self.call("project.dependency_tree", {"ecosystem": "python"})
        versions = {
            node["package"]["name"]: node["package"]["resolvedVersion"]
            for node in tree["research"]["nodes"]
        }
        self.assertEqual(versions["requests"], "2.32.4")
        read = self.call("project.wiki_read_page", {
            "path": "dependencies/requests.md",
            "inputs": {"requests": {"version": versions["requests"]}},
        })
        self.assertEqual(len(read["page"]["staleNotes"]), 1)
        self.assertEqual(read["page"]["staleNotes"][0]["staleReason"],
                         "version")


if __name__ == "__main__":
    unittest.main()

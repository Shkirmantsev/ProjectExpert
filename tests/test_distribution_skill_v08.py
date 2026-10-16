"""Distribution skill content tests for Change Package I.

The v0.8 refinement (``improve-ingestion-retrieval-local-models``,
Change Package I) updates the agent skill
``distribution/skills/project-intelligence/SKILL.md`` to document
the new retrieval semantics: protected exact candidates, reserve
escalation, automatic support context attachment, broad
repository scans as a fallback, and the debug-only trace tool.

These tests assert the canonical skill frontmatter is intact and
the new section is present so a follow-up edit cannot silently
drop the v0.8 contract.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


__all__ = ["DistributionSkillContentTests"]


_SKILL_PATH = Path(__file__).resolve().parents[1] / (
    "distribution/skills/project-intelligence/SKILL.md"
)


class DistributionSkillContentTests(unittest.TestCase):

    def test_skill_file_exists(self) -> None:
        self.assertTrue(_SKILL_PATH.exists(),
                        f"skill file missing: {_SKILL_PATH}")

    def test_skill_frontmatter_intact(self) -> None:
        text = _SKILL_PATH.read_text(encoding="utf-8")
        # The frontmatter must still pin the v0.8 contract.
        self.assertIn("name: project-intelligence", text)
        self.assertIn("knowledge-schema:", text)
        self.assertIn("mcp-api:", text)
        # The knowledge-schema constraint accepts the v0.8 line;
        # the v0.7 lower bound is preserved so existing skills
        # keep loading.
        schema_line = text.split("knowledge-schema:", 1)[1].split("\n", 1)[0]
        self.assertIn(">=0.7.0", schema_line)
        self.assertIn("<1.0.0", schema_line)

    def test_skill_documents_protected_candidates(self) -> None:
        text = _SKILL_PATH.read_text(encoding="utf-8")
        # The new section must call out protected exact candidates
        # so an agent never overrides a protected hit silently.
        self.assertRegex(
            text, r"\*\*Protected exact candidates\.\*\*",
        )

    def test_skill_documents_reserve_escalation(self) -> None:
        text = _SKILL_PATH.read_text(encoding="utf-8")
        self.assertRegex(
            text, r"\*\*Reserve escalation\.\*\*",
        )

    def test_skill_documents_support_context(self) -> None:
        text = _SKILL_PATH.read_text(encoding="utf-8")
        self.assertRegex(
            text, r"\*\*Support context is attached automatically\.\*\*",
        )

    def test_skill_documents_conflicts_surface(self) -> None:
        text = _SKILL_PATH.read_text(encoding="utf-8")
        self.assertRegex(
            text, r"\*\*Conflicts are surfaced\.\*\*",
        )

    def test_skill_documents_trace_tool(self) -> None:
        text = _SKILL_PATH.read_text(encoding="utf-8")
        self.assertRegex(
            text, r"\*\*Trace tool \(debug / admin only\)\.\*\*",
        )
        # The trace tool must be listed as a debug-only call;
        # the read-only-vs-write section should also exclude it
        # from the public approval-free set.
        self.assertIn("project.get_retrieval_trace", text)
        self.assertIn("DebugModeRequiredError", text)

    def test_skill_documents_broad_scans_fallback(self) -> None:
        text = _SKILL_PATH.read_text(encoding="utf-8")
        # The fallback sentence may span multiple lines; use a
        # DOTALL regex so the .* matches newlines.
        self.assertRegex(
            text, re.compile(
                r"Broad repository scans.*\*\*fallback\*\*",
                re.DOTALL,
            ),
        )

    def test_skill_keeps_legacy_behaviour_contract(self) -> None:
        # Backwards compatibility: the original 10-step contract
        # must still be present so existing agents keep working.
        text = _SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("Behaviour contract (10 steps)", text)
        # The 10-step contract lists specific tool names.
        for tool in (
            "project.search",
            "project.retrieve_context",
            "project.build_task_context",
            "project.materialize_knowledge",
        ):
            self.assertIn(tool, text)

    def test_skill_section_headings_are_unique(self) -> None:
        text = _SKILL_PATH.read_text(encoding="utf-8")
        # Find all ``## `` headings and assert no duplicate.
        headings = re.findall(r"(?m)^## (.+)$", text)
        self.assertEqual(len(headings), len(set(headings)),
                         f"duplicate skill headings: {headings}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
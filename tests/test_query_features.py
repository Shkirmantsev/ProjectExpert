"""QueryFeatures value-object tests (Change Package A1).

Covers the additive ``QueryFeatures`` contract from
``openspec/changes/improve-ingestion-retrieval-local-models/specs/2026-10-04-hybrid-retrieval/spec.md``:
identifier extraction via the shared ``IDENTIFIER_PATTERN``, quoted
phrase extraction, free-text detection and safe handling of empty /
``None`` input, plus the additive ``RetrievalHit.selection_state``
field validation.
"""

from __future__ import annotations

import unittest

from pi_platform.core.retrieval.query_features import (
    QUOTED_PHRASE_PATTERN,
    QueryFeatures,
)
from pi_platform.ports.retrieval.hybrid_retrieval import (
    SELECTION_STATE_ALLOWED,
    RetrievalHit,
)


class QueryFeaturesFromTextTests(unittest.TestCase):
    """``QueryFeatures.from_text`` extraction behaviour."""

    def test_pure_identifier_has_no_free_text(self):
        qf = QueryFeatures.from_text("ILO-5193")
        self.assertEqual(qf.identifiers, ("ILO-5193",))
        self.assertFalse(qf.has_free_text)
        self.assertEqual(qf.quoted_phrases, ())

    def test_mixed_identifier_and_prose_has_free_text(self):
        qf = QueryFeatures.from_text("Where is ILO-5193 implemented?")
        self.assertEqual(qf.identifiers, ("ILO-5193",))
        self.assertTrue(qf.has_free_text)

    def test_snake_case_identifier_with_prose(self):
        qf = QueryFeatures.from_text(
            "Explain PSB_FINISH_PACK timeout behavior",
        )
        self.assertIn("PSB_FINISH_PACK", qf.identifiers)
        self.assertTrue(qf.has_free_text)

    def test_version_identifier_with_pascal_case_word(self):
        qf = QueryFeatures.from_text("GEN_3.0.03 FinishPack")
        # The shared IDENTIFIER_PATTERN extracts the snake_case stem
        # ``GEN_3`` from the dotted version token; the important
        # routing signal is that an identifier is present and prose
        # remains.
        self.assertIn("GEN_3", qf.identifiers)
        self.assertTrue(qf.has_free_text)

    def test_identifiers_keep_stable_first_seen_order(self):
        qf = QueryFeatures.from_text("Check ILO-5193 then PSB_FINISH_PACK")
        self.assertEqual(qf.identifiers, ("ILO-5193", "PSB_FINISH_PACK"))

    def test_quoted_phrases_extracted(self):
        qf = QueryFeatures.from_text('find "finish pack timeout" details')
        self.assertEqual(qf.quoted_phrases, ("finish pack timeout",))
        self.assertTrue(qf.has_free_text)

    def test_quoted_phrase_pattern_bounds(self):
        match = QUOTED_PHRASE_PATTERN.search('say "abc" now')
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "abc")
        self.assertIsNone(
            QUOTED_PHRASE_PATTERN.search("no quotes present"),
        )

    def test_empty_text_is_safe(self):
        qf = QueryFeatures.from_text("")
        self.assertEqual(qf.identifiers, ())
        self.assertEqual(qf.quoted_phrases, ())
        self.assertFalse(qf.has_free_text)

    def test_none_text_is_safe(self):
        qf = QueryFeatures.from_text(None)  # type: ignore[arg-type]
        self.assertEqual(qf.identifiers, ())
        self.assertFalse(qf.has_free_text)

    def test_free_text_only_query(self):
        qf = QueryFeatures.from_text("how does packing work")
        self.assertEqual(qf.identifiers, ())
        self.assertTrue(qf.has_free_text)


class SelectionStateFieldTests(unittest.TestCase):
    """``RetrievalHit.selection_state`` additive field validation."""

    def test_default_selection_state_is_empty(self):
        hit = RetrievalHit(chunkId="c-1", score=0.5, source="dense")
        self.assertEqual(hit.selection_state, "")
        self.assertIn("", SELECTION_STATE_ALLOWED)

    def test_protected_selection_state_accepted(self):
        hit = RetrievalHit(
            chunkId="c-1", score=1.0, source="exact",
            selection_state="PROTECTED",
        )
        self.assertEqual(hit.selection_state, "PROTECTED")

    def test_invalid_selection_state_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            RetrievalHit(
                chunkId="c-1", score=0.5, source="dense",
                selection_state="GRAPH",
            )
        self.assertIn("selection_state", str(ctx.exception))

    def test_selection_state_allowed_set(self):
        self.assertEqual(
            SELECTION_STATE_ALLOWED,
            ("", "PRIMARY", "RESERVE", "PROTECTED", "SUPPORT",
             "DROPPED_DUPLICATE"),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

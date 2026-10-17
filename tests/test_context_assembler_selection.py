"""Context assembler selection-awareness tests (Change Package A4).

Covers the context-assembler delta spec scenarios: protected direct
evidence before SUPPORT, near-duplicate collapse with provenance,
support-hit population, selection summaries and the byte-identical
legacy path when no selection result / support evidence is supplied.
"""

from __future__ import annotations

import unittest

from pi_platform.core.canonical.value_types import KnowledgeState, Metadata
from pi_platform.core.retrieval.context_assembler import (
    ContextAssemblerCore,
    DROP_NEAR_DUPLICATE_COLLAPSED,
)
from pi_platform.core.retrieval.multi_stage_retrieval import (
    SupportEvidence,
)
from pi_platform.ports.retrieval.context_assembler import ContextBudget
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery
from pi_platform.ports.retrieval.selection import SelectionResult


__all__ = [
    "ProtectedBeforeSupportTests",
    "AssemblerLegacyPathTests",
    "AssemblerDedupTests",
    "SupportHitsTests",
]


def _hit(
    chunk_id: str, *, score: float = 0.5, document_id: str = "DOC-0",
    content_hash: str = "", token_estimate: int = 64,
    selection_state: str = "",
) -> RetrievalHit:
    return RetrievalHit(
        chunkId=chunk_id, score=score, source="hybrid",
        contentHash=content_hash or chunk_id,
        metadata=Metadata(
            documentId=document_id, version="0.0.0", language="en",
        ),
        knowledgeState=KnowledgeState.VERIFIED,
        tokenEstimate=token_estimate,
        selection_state=selection_state,
    )


def _query() -> RetrievalQuery:
    return RetrievalQuery(text="q", top_k=5, contextBudget=1024)


class ProtectedBeforeSupportTests(unittest.TestCase):
    """Protected evidence lands in the bundle before any SUPPORT."""

    def test_protected_evidence_before_support(self):
        assembler = ContextAssemblerCore()
        protected_hit = _hit(
            "p-1", score=0.1, token_estimate=200,
            selection_state="PROTECTED",
        )
        support = SupportEvidence(
            chunk_id="sup-1", snippet="support snippet for p-1",
            evidence_kind="graph", source_document_id="DOC-0",
        )
        selection_result = SelectionResult(
            protected=(protected_hit,), primary=(), reserve=(),
        )
        bundle = assembler.assemble(
            (),
            contextBudget=ContextBudget(tokenLimit=1024),
            query=_query(),
            support_evidence=(support,),
            selection_result=selection_result,
        )
        self.assertIn(protected_hit, bundle.protected_hits)
        self.assertIn(protected_hit, bundle.hits)
        support_items = [
            item for item in bundle.hits
            if isinstance(item, SupportEvidence)
        ]
        self.assertEqual(len(support_items), 1)
        self.assertLess(
            bundle.hits.index(protected_hit),
            bundle.hits.index(support_items[0]),
        )
        # RESERVE candidates are only added when the budget is not
        # exhausted (none here).
        self.assertEqual(bundle.reserve_hits, ())


class AssemblerLegacyPathTests(unittest.TestCase):
    """The legacy path is byte-identical when no v2 input is given."""

    def test_legacy_path_byte_identical(self):
        assembler = ContextAssemblerCore()
        hits = [
            _hit("a", score=0.9, token_estimate=32),
            _hit("b", score=0.8, token_estimate=32),
            _hit("a", score=0.7, token_estimate=32),  # duplicate id
            _hit("c", score=0.6, token_estimate=32),
        ]
        budget = ContextBudget(tokenLimit=100)
        query = _query()
        legacy = assembler.assemble(
            hits, contextBudget=budget, query=query,
        )
        explicit = assembler.assemble(
            hits, contextBudget=budget, query=query,
            support_evidence=(), selection_result=None,
        )
        self.assertEqual(legacy.hits, explicit.hits)
        self.assertEqual(legacy.budgetUsed, explicit.budgetUsed)
        self.assertEqual(legacy.dropReasons, explicit.dropReasons)
        self.assertEqual(legacy.explanations, explicit.explanations)
        # The legacy dedup reason stays ``deduplicated``; the new
        # collapse reason only appears on the selection-aware path.
        self.assertIn("deduplicated", legacy.dropReasons)
        self.assertNotIn(DROP_NEAR_DUPLICATE_COLLAPSED,
                         legacy.dropReasons)
        # Legacy bundles carry no selection summary.
        self.assertEqual(legacy.selection_summary, {})


class AssemblerDedupTests(unittest.TestCase):
    """Near-duplicate collapse preserves the collapsed provenance."""

    def test_dedup_preserves_provenance(self):
        assembler = ContextAssemblerCore()
        winner = _hit("w-1", score=0.9, content_hash="h-dup")
        loser_1 = _hit("l-1", score=0.8, content_hash="h-dup")
        loser_2 = _hit("l-2", score=0.7, content_hash="h-dup")
        selection_result = SelectionResult(
            primary=(winner, loser_1, loser_2), reserve=(), protected=(),
        )
        bundle = assembler.assemble(
            (),
            contextBudget=ContextBudget(tokenLimit=1024),
            query=_query(),
            support_evidence=(),
            selection_result=selection_result,
        )
        hit_ids = [h.chunkId for h in bundle.hits]
        self.assertEqual(hit_ids, ["w-1"])
        self.assertIn(DROP_NEAR_DUPLICATE_COLLAPSED, bundle.dropReasons)
        collapsed_lines = [
            line for line in bundle.explanations
            if line.startswith("collapsed_into:")
        ]
        self.assertEqual(
            collapsed_lines,
            ["collapsed_into:w-1", "collapsed_into:w-1"],
        )
        dropped_ids = [h.chunkId for h in bundle.droppedHits]
        self.assertEqual(dropped_ids, ["l-1", "l-2"])


class SupportHitsTests(unittest.TestCase):
    """Support evidence is surfaced in the bundle and the summary."""

    def test_support_hits_populated(self):
        assembler = ContextAssemblerCore()
        primary_hit = _hit("p-1", score=0.9)
        support = (
            SupportEvidence(
                chunk_id="sup-1", snippet="graph support",
                evidence_kind="graph", source_document_id="DOC-0",
            ),
            SupportEvidence(
                chunk_id="sup-2", snippet="hierarchy support",
                evidence_kind="hierarchy", source_document_id="DOC-0",
            ),
        )
        selection_result = SelectionResult(
            primary=(primary_hit,), reserve=(), protected=(),
        )
        bundle = assembler.assemble(
            (),
            contextBudget=ContextBudget(tokenLimit=1024),
            query=_query(),
            support_evidence=support,
            selection_result=selection_result,
        )
        self.assertEqual(len(bundle.support_hits), 2)
        self.assertEqual(bundle.selection_summary["support"], 2)
        self.assertEqual(bundle.selection_summary["primary"], 1)
        self.assertEqual(bundle.selection_summary["reserve"], 0)
        self.assertEqual(bundle.selection_summary["protected"], 0)
        support_in_hits = [
            item for item in bundle.hits
            if isinstance(item, SupportEvidence)
        ]
        self.assertEqual(len(support_in_hits), 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

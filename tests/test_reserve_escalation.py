"""Reserve escalation tests (Change Package A4).

Covers the context-assembler reserve-escalation scenario: when the
primary pool covers only part of the available subtopics (distinct
source documents), the assembler pulls RESERVE candidates until every
subtopic has at least one evidence link or the budget is exhausted.
"""

from __future__ import annotations

import unittest

from pi_platform.core.canonical.value_types import KnowledgeState, Metadata
from pi_platform.core.retrieval.context_assembler import ContextAssemblerCore
from pi_platform.ports.retrieval.context_assembler import ContextBudget
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery
from pi_platform.ports.retrieval.selection import SelectionResult


__all__ = [
    "ReserveEscalationTests",
]


def _hit(
    chunk_id: str, *, score: float, document_id: str,
    token_estimate: int = 64,
) -> RetrievalHit:
    return RetrievalHit(
        chunkId=chunk_id, score=score, source="hybrid",
        contentHash=chunk_id,
        metadata=Metadata(
            documentId=document_id, version="0.0.0", language="en",
        ),
        knowledgeState=KnowledgeState.VERIFIED,
        tokenEstimate=token_estimate,
    )


class ReserveEscalationTests(unittest.TestCase):
    """RESERVE escalates for uncovered subtopics."""

    def test_reserve_escalation_for_subtopic(self):
        assembler = ContextAssemblerCore()
        # The primary set covers only DOC-1 (subquestion 1); the
        # reserve pool carries the DOC-2 evidence (subquestion 2).
        primary_hit = _hit(
            "p-1", score=0.9, document_id="DOC-1",
        )
        reserve_hit = _hit(
            "r-1", score=0.5, document_id="DOC-2",
        )
        same_doc_reserve = _hit(
            "r-2", score=0.4, document_id="DOC-1",
        )
        selection_result = SelectionResult(
            primary=(primary_hit,),
            reserve=(reserve_hit, same_doc_reserve),
            protected=(),
        )
        bundle = assembler.assemble(
            (),
            contextBudget=ContextBudget(tokenLimit=1024),
            query=RetrievalQuery(text="q", top_k=5, contextBudget=1024),
            support_evidence=(),
            selection_result=selection_result,
        )
        hit_ids = [h.chunkId for h in bundle.hits]
        hit_docs = {
            h.metadata.documentId for h in bundle.hits
        }
        # Both subquestions end up with at least one evidence link.
        self.assertIn("p-1", hit_ids)
        self.assertIn("r-1", hit_ids)
        self.assertEqual(hit_docs, {"DOC-1", "DOC-2"})
        # The already-covered DOC-1 reserve candidate is not pulled.
        self.assertNotIn("r-2", hit_ids)
        self.assertEqual(bundle.reserve_hits, (reserve_hit,))
        # Escalation order: primary first, escalated reserve after.
        self.assertLess(hit_ids.index("p-1"), hit_ids.index("r-1"))

    def test_no_escalation_when_budget_exhausted(self):
        assembler = ContextAssemblerCore()
        primary_hit = _hit(
            "p-1", score=0.9, document_id="DOC-1", token_estimate=96,
        )
        reserve_hit = _hit(
            "r-1", score=0.5, document_id="DOC-2", token_estimate=64,
        )
        selection_result = SelectionResult(
            primary=(primary_hit,), reserve=(reserve_hit,),
            protected=(),
        )
        bundle = assembler.assemble(
            (),
            contextBudget=ContextBudget(tokenLimit=100),
            query=RetrievalQuery(text="q", top_k=5, contextBudget=100),
            support_evidence=(),
            selection_result=selection_result,
        )
        hit_ids = [h.chunkId for h in bundle.hits]
        self.assertIn("p-1", hit_ids)
        self.assertNotIn("r-1", hit_ids)
        self.assertEqual(bundle.reserve_hits, ())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

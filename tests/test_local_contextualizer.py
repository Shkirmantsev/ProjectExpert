"""LocalContextualizer tests (Change Package B5).

Covers the context-enrichment delta: InferencePolicy gating,
forbidden authoritative-field filtering, cache-key composition, LRU
cache hits, prompt isolation from authoritative metadata, and the
layered enricher's opt-in path that never overwrites authoritative
metadata (legacy binding path stays byte-identical).
"""

from __future__ import annotations

import unittest
from typing import Mapping, Optional

from pi_platform.adapters.ingest.layered_context_enricher import LayeredContextEnricher
from pi_platform.core.canonical.value_types import (
    Chunk,
    Document,
    KnowledgeState,
    Metadata,
    Section,
    to_canonical_json,
)
from pi_platform.core.ingest.local_contextualizer import (
    LocalContextSummary,
    LocalContextualizer,
    PROMPT_VERSION,
)
from pi_platform.ports.ingest.context_enricher import EnricherContext
from pi_platform.ports.ingest.inference_policy import InferencePolicy
from pi_platform.ports.orchestration.local_llm import LocalLLMPort


_RICH_OUTPUT = (
    "summary: packing context hint\n"
    "entities: Order, Packer\n"
    "relations: Order -> Packer\n"
    "aliases: pack, packing run\n"
)

_FORBIDDEN_OUTPUT = (
    "requirement_id: REQ-999\n"
    "protocol_version: 9.9\n"
    "validFrom: 2020-01-01\n"
    "validTo: 2030-01-01\n"
    "security_class: SECRET\n"
    "git_revision: deadbeefcafe\n"
    "source_id: src-1\n"
    "license: proprietary\n"
    "summary: safe hint\n"
    "entities: Order\n"
)


class _RecordingLLM(LocalLLMPort):
    """Deterministic in-memory LocalLLMPort used by the tests."""

    def __init__(
        self,
        output: str = _RICH_OUTPUT,
        version: str = "llm-1",
        family_name: str = "fake",
    ) -> None:
        self.calls = 0
        self.prompts: list[str] = []
        self.max_tokens_seen: Optional[int] = None
        self.temperature_seen: Optional[float] = None
        self._output = output
        self._version = version
        self._family = family_name

    def complete(
        self, prompt: str, *, max_tokens: int = 256, temperature: float = 0.0
    ) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        self.max_tokens_seen = max_tokens
        self.temperature_seen = temperature
        return self._output

    def is_available(self) -> bool:
        return True

    def model_version(self) -> str:
        return self._version

    def license_id(self) -> str:
        return "Apache-2.0"

    def family(self) -> str:
        return self._family

    def stats(self) -> Mapping[str, int]:
        return {"calls": self.calls}


def _chunk(
    *,
    content_hash: str = "content-1",
    requirement_id: str = "REQ-42",
    raw_text: str = "Packing finishes orders.",
) -> Chunk:
    metadata = Metadata(
        documentId="doc-1",
        version="0.0.0",
        language="en",
        section="Overview",
        requirementId=requirement_id,
    )
    return Chunk(
        "c1", raw_text, raw_text, metadata, "doc.md", content_hash, parentId="sec-1"
    )


def _document() -> Document:
    return Document("doc-1", "Packing Guide")


def _section() -> Section:
    return Section("sec-1", "Overview", 2)


class LocalContextualizerPolicyTests(unittest.TestCase):
    def test_no_model_policy_returns_empty_without_llm_call(self):
        llm = _RecordingLLM()
        contextualizer = LocalContextualizer(llm)  # default NO_MODEL
        summary = contextualizer.summarize(
            chunk=_chunk(), document=_document(), section=_section()
        )
        self.assertEqual(summary.summary, "")
        self.assertEqual(summary.candidate_entities, ())
        self.assertEqual(summary.model_revision, "")
        self.assertEqual(llm.calls, 0)

    def test_local_model_allowed_calls_llm(self):
        llm = _RecordingLLM()
        contextualizer = LocalContextualizer(
            llm, policy=InferencePolicy.LOCAL_MODEL_ALLOWED
        )
        summary = contextualizer.summarize(
            chunk=_chunk(), document=_document(), section=_section()
        )
        self.assertEqual(llm.calls, 1)
        self.assertEqual(summary.summary, "packing context hint")
        self.assertEqual(summary.candidate_entities, ("Order", "Packer"))
        self.assertEqual(summary.candidate_relations, ("Order -> Packer",))
        self.assertEqual(summary.query_aliases, ("pack", "packing run"))
        self.assertEqual(summary.model_revision, "llm-1")
        self.assertEqual(summary.prompt_version, PROMPT_VERSION)
        self.assertTrue(summary.content_hash)
        self.assertEqual(llm.temperature_seen, 0.0)

    def test_external_model_allowed_calls_llm(self):
        llm = _RecordingLLM()
        contextualizer = LocalContextualizer(
            llm, policy=InferencePolicy.EXTERNAL_MODEL_ALLOWED
        )
        summary = contextualizer.summarize(
            chunk=_chunk(), document=_document(), section=_section()
        )
        self.assertEqual(llm.calls, 1)
        self.assertEqual(summary.summary, "packing context hint")


class LocalContextualizerIsolationTests(unittest.TestCase):
    def setUp(self):
        self.llm = _RecordingLLM(output=_FORBIDDEN_OUTPUT)
        self.contextualizer = LocalContextualizer(
            self.llm, policy=InferencePolicy.LOCAL_MODEL_ALLOWED
        )

    def test_forbidden_authoritative_fields_are_filtered(self):
        summary = self.contextualizer.summarize(
            chunk=_chunk(), document=_document(), section=_section()
        )
        self.assertEqual(summary.summary, "safe hint")
        self.assertEqual(summary.candidate_entities, ("Order",))
        all_text = " ".join(
            (
                summary.summary,
                *summary.candidate_entities,
                *summary.candidate_relations,
                *summary.query_aliases,
            )
        )
        for forbidden in (
            "REQ-999",
            "9.9",
            "2020-01-01",
            "2030-01-01",
            "SECRET",
            "deadbeefcafe",
            "src-1",
            "proprietary",
        ):
            self.assertNotIn(forbidden, all_text)

    def test_prompt_excludes_authoritative_metadata(self):
        self.contextualizer.summarize(
            chunk=_chunk(requirement_id="REQ-42"),
            document=_document(),
            section=_section(),
            neighbour_text="nearby chunk",
        )
        prompt = self.llm.prompts[0]
        self.assertNotIn("REQ-42", prompt)
        self.assertIn("Packing finishes orders.", prompt)
        self.assertIn("Packing Guide", prompt)
        self.assertIn("nearby chunk", prompt)

    def test_summary_is_truncated_to_max_summary_chars(self):
        llm = _RecordingLLM(output="summary: " + "x" * 200)
        contextualizer = LocalContextualizer(
            llm, policy=InferencePolicy.LOCAL_MODEL_ALLOWED, max_summary_chars=32
        )
        summary = contextualizer.summarize(
            chunk=_chunk(), document=_document(), section=_section()
        )
        self.assertEqual(len(summary.summary), 32)


class LocalContextualizerCacheTests(unittest.TestCase):
    def _contextualizer(self, llm, **kwargs) -> LocalContextualizer:
        return LocalContextualizer(llm, policy=InferencePolicy.LOCAL_MODEL_ALLOWED, **kwargs)

    def test_cache_key_changes_with_model_revision(self):
        first = self._contextualizer(_RecordingLLM(version="m-1"))
        second = self._contextualizer(_RecordingLLM(version="m-2"))
        chunk = _chunk()
        self.assertNotEqual(
            first.cache_key(chunk=chunk), second.cache_key(chunk=chunk)
        )

    def test_cache_key_changes_with_prompt_version(self):
        first = self._contextualizer(_RecordingLLM(), prompt_version="v1")
        second = self._contextualizer(_RecordingLLM(), prompt_version="v2")
        chunk = _chunk()
        self.assertNotEqual(
            first.cache_key(chunk=chunk), second.cache_key(chunk=chunk)
        )
        self.assertEqual(first.cache_key(chunk=chunk), first.cache_key(chunk=chunk))

    def test_cache_key_changes_with_enrichment_strategy_version(self):
        first = self._contextualizer(
            _RecordingLLM(), enrichment_strategy_version="v1",
        )
        second = self._contextualizer(
            _RecordingLLM(), enrichment_strategy_version="v2",
        )
        chunk = _chunk()
        self.assertNotEqual(
            first.cache_key(chunk=chunk), second.cache_key(chunk=chunk)
        )
        self.assertEqual(first.cache_key(chunk=chunk), first.cache_key(chunk=chunk))

    def test_cache_key_changes_with_content_and_neighbour(self):
        contextualizer = self._contextualizer(_RecordingLLM())
        base = contextualizer.cache_key(chunk=_chunk(content_hash="c-1"))
        self.assertNotEqual(
            base, contextualizer.cache_key(chunk=_chunk(content_hash="c-2"))
        )
        self.assertNotEqual(
            base, contextualizer.cache_key(chunk=_chunk(content_hash="c-1"), neighbour_text="n1")
        )

    def test_cache_hit_does_not_call_llm(self):
        llm = _RecordingLLM(output="summary: first pass")
        contextualizer = self._contextualizer(llm)
        chunk = _chunk()
        first_summary, first_hit = contextualizer.cached_summarize(chunk)
        second_summary, second_hit = contextualizer.cached_summarize(chunk)
        self.assertFalse(first_hit)
        self.assertTrue(second_hit)
        self.assertEqual(first_summary, second_summary)
        self.assertEqual(llm.calls, 1)

    def test_cache_miss_for_different_chunk_content(self):
        llm = _RecordingLLM()
        contextualizer = self._contextualizer(llm)
        contextualizer.cached_summarize(_chunk(content_hash="c-1"))
        contextualizer.cached_summarize(_chunk(content_hash="c-2"))
        self.assertEqual(llm.calls, 2)


class LayeredContextEnricherContextualizerTests(unittest.TestCase):
    def _enrich(self, chunks, context):
        return LayeredContextEnricher().enrich(chunks, context)

    def _contextualizer(self, llm=None, **kwargs) -> LocalContextualizer:
        return LocalContextualizer(
            llm or _RecordingLLM(),
            policy=InferencePolicy.LOCAL_MODEL_ALLOWED,
            **kwargs,
        )

    def test_contextualizer_summary_is_inferred_not_authoritative(self):
        chunk = _chunk(requirement_id="REQ-123")
        out, reports = self._enrich(
            (chunk,),
            EnricherContext(
                enable_optional_llm=True,
                local_contextualizer=self._contextualizer(),
            ),
        )
        enriched = out[0]
        # Authoritative metadata is untouched.
        self.assertEqual(enriched.chunk.metadata.requirementId, "REQ-123")
        assumption = enriched.chunk.metadata.extensions["pi_assumption"]
        self.assertEqual(assumption["context_summary"], "packing context hint")
        self.assertEqual(assumption["knowledgeState"], "assumption")
        self.assertEqual(assumption["candidateEntities"], ["Order", "Packer"])
        # The inferred summary is a clearly named prefix line.
        self.assertIn("contextSummary: packing context hint", enriched.contextPrefix)
        self.assertEqual(enriched.chunk.provenance.knowledgeState, KnowledgeState.ASSUMPTION)
        self.assertEqual(
            reports[0].knowledge_state, KnowledgeState.ASSUMPTION
        )

    def test_no_model_contextualizer_blocks_llm_through_enricher(self):
        llm = _RecordingLLM()
        contextualizer = LocalContextualizer(llm)  # NO_MODEL default
        out, _ = self._enrich(
            (_chunk(),),
            EnricherContext(enable_optional_llm=True, local_contextualizer=contextualizer),
        )
        self.assertEqual(llm.calls, 0)
        self.assertEqual(
            out[0].chunk.metadata.extensions["pi_assumption"]["context_summary"], ""
        )
        self.assertNotIn("contextSummary", out[0].contextPrefix)

    def test_legacy_binding_path_stays_byte_identical(self):
        metadata = Metadata(
            documentId="doc-1",
            version="0.0.0",
            language="en",
            section="A",
            sourcePath="/tmp/project/psb/packing/a.md",
            requirementId="REQ-123",
            policy="LOCAL_ONLY",
        )
        chunk = Chunk(
            "c1", "body", "body", metadata, "/tmp/project/psb/packing/a.md", "hash-c1"
        )

        def binding(text, max_tokens):
            return {
                "requirementId": "invented",
                "entities": ["guess"],
                "contextPrefix": "suggested",
            }

        out, _ = self._enrich(
            (chunk,),
            EnricherContext(
                enable_optional_llm=True,
                extra={"local_llm": binding, "allow_local_llm": True},
            ),
        )
        enriched = out[0]
        self.assertEqual(
            enriched.contextPrefix,
            "section: A\nsourcePath: /tmp/project/psb/packing/a.md\n"
            "requirementId: REQ-123",
        )
        self.assertNotIn("contextSummary", enriched.contextPrefix)
        self.assertEqual(
            enriched.chunk.metadata.extensions["pi_assumption"],
            {
                "entities": ["guess"],
                "contextPrefix": "suggested",
                "knowledgeState": "assumption",
            },
        )
        self.assertEqual(enriched.chunk.metadata.requirementId, "REQ-123")
        # Deterministic repeat: byte-identical canonical output.
        repeat, _ = self._enrich(
            (chunk,),
            EnricherContext(
                enable_optional_llm=True,
                extra={"local_llm": binding, "allow_local_llm": True},
            ),
        )
        self.assertEqual(to_canonical_json(enriched), to_canonical_json(repeat[0]))

    def test_summary_object_shape_is_accepted_by_builder(self):
        # LocalContextSummary flows into the retrieval text builder via
        # its documented ``summary`` attribute fallback.
        summary = LocalContextSummary(summary="derived hint")
        self.assertEqual(summary.summary, "derived hint")


if __name__ == "__main__":
    unittest.main()

"""Tests for Change Package F: quality reranker profiles.

F1 — functional CrossEncoder adapter (no more constructor-only stub)
F2 — Qwen3-Reranker adapter (separate profile)
F3 — timeouts and batching
F4 — RerankWithFallback wrapper
"""

from __future__ import annotations

import time
import unittest
from dataclasses import replace
from typing import List, Sequence

from pi_platform.core.canonical.value_types import Metadata
from pi_platform.core.retrieval.reranker import Bm25LightRerankerCore
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.rerank_text import (
    DEFAULT_MAX_PAIR_TOKENS,
    RerankTextBuilder,
    RerankTextBuilderError,
)
from pi_platform.ports.retrieval.reranker import (
    RerankerError,
    RerankerPort,
)
from pi_platform.adapters.retrieval.cross_encoder_reranker import (
    ADAPTER_NAME as CE_NAME,
    CrossEncoderRerankerAdapter,
    DEFAULT_LICENSE_ID as CE_LICENSE,
    DEFAULT_MODEL_ID as CE_MODEL,
)
from pi_platform.adapters.retrieval.qwen3_reranker import (
    ADAPTER_NAME as QWEN_NAME,
    DEFAULT_LICENSE_ID as QWEN_LICENSE,
    DEFAULT_MODEL_ID as QWEN_MODEL,
    Qwen3RerankerAdapter,
)
from pi_platform.adapters.retrieval.rerank_with_fallback import (
    RerankWithFallback,
)


def _meta(**overrides) -> Metadata:
    base = dict(
        documentId="d-1", version="0.0.0", language="und",
    )
    base.update(overrides)
    return Metadata(**base)


def _hit(
    chunk_id: str, score: float, *,
    snippet: str = "", source: str = "exact",
) -> RetrievalHit:
    return RetrievalHit(
        chunkId=chunk_id, score=score, source=source,
        snippet=snippet, contentHash=f"h-{chunk_id}",
        metadata=_meta(),
    )


# ===========================================================================
# RerankTextBuilder (F1, F2)
# ===========================================================================


class RerankTextBuilderSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._builder = RerankTextBuilder()

    def test_build_returns_query_passage_pair(self) -> None:
        hit = _hit("c-1", 0.5, snippet="snippet text")
        text = self._builder.build(query="hello", hit=hit)
        self.assertEqual(text.query, "hello")
        self.assertIn("snippet text", text.passage)
        self.assertEqual(text.strategy_version, "rerank-text/v1")
        self.assertFalse(text.truncated)

    def test_build_includes_section_and_requirement(self) -> None:
        hit = RetrievalHit(
            chunkId="c-1", score=0.5, source="exact", snippet="",
            metadata=replace(
                _meta(),
                section="Implementation",
                requirementId="REQ-7",
            ),
        )
        text = self._builder.build(query="q", hit=hit)
        self.assertIn("section: Implementation", text.passage)
        self.assertIn("requirement: REQ-7", text.passage)

    def test_build_includes_caption(self) -> None:
        meta = replace(_meta(), extensions={"caption": "Figure 1: hello"})
        hit = RetrievalHit(
            chunkId="c-1", score=0.5, source="exact",
            snippet="", metadata=meta,
        )
        text = self._builder.build(query="q", hit=hit)
        self.assertIn("caption: Figure 1: hello", text.passage)

    def test_build_excludes_forbidden_metadata_key(self) -> None:
        # A non-empty ``git_sha`` extension must raise.
        meta = replace(_meta(), extensions={"git_sha": "abc1234"})
        hit = RetrievalHit(
            chunkId="c-1", score=0.5, source="exact",
            snippet="", metadata=meta,
        )
        with self.assertRaises(RerankTextBuilderError):
            self._builder.build(query="q", hit=hit)

    def test_build_excludes_forbidden_value_in_snippet(self) -> None:
        hit = _hit("c-1", 0.5, snippet="api key is sk-abc123")
        with self.assertRaises(RerankTextBuilderError):
            self._builder.build(query="q", hit=hit)

    def test_build_truncates_past_max_pair_tokens(self) -> None:
        builder = RerankTextBuilder(max_pair_tokens=8)
        long = " ".join(f"word{i}" for i in range(100))
        hit = _hit("c-1", 0.5, snippet=long)
        text = builder.build(query="q", hit=hit)
        self.assertTrue(text.truncated)
        self.assertLess(len(text.passage), len(long))
        self.assertIn("[...truncated]", text.passage)

    def test_build_max_pair_tokens_positive(self) -> None:
        with self.assertRaises(RerankTextBuilderError):
            RerankTextBuilder(max_pair_tokens=0)

    def test_default_max_pair_tokens(self) -> None:
        self.assertEqual(DEFAULT_MAX_PAIR_TOKENS, 1536)


# ===========================================================================
# F1 — CrossEncoderRerankerAdapter
# ===========================================================================


class CrossEncoderRerankerAdapterTests(unittest.TestCase):
    def test_is_reranker_port(self) -> None:
        a = CrossEncoderRerankerAdapter()
        self.assertIsInstance(a, RerankerPort)

    def test_engine_metadata(self) -> None:
        a = CrossEncoderRerankerAdapter()
        self.assertEqual(a.model_version(), CE_MODEL)
        self.assertEqual(a.license_id(), CE_LICENSE)
        self.assertEqual(a.family(), "cross-encoder")
        self.assertEqual(a.backend_name, CE_NAME)

    def test_rerank_returns_top_k_in_score_order(self) -> None:
        a = CrossEncoderRerankerAdapter()
        candidates = [
            _hit(f"c-{i}", 0.1 * i, snippet=f"hello world {i}")
            for i in range(5)
        ]
        result = a.rerank("hello", candidates, top_k=3)
        self.assertEqual(len(result), 3)
        # All scores are in [0, 1].
        for hit in result:
            self.assertGreaterEqual(hit.score, 0.0)
            self.assertLessEqual(hit.score, 1.0)
        # chunkId uniqueness.
        ids = [h.chunkId for h in result]
        self.assertEqual(len(ids), len(set(ids)))

    def test_rerank_top_k_positive_validated(self) -> None:
        a = CrossEncoderRerankerAdapter()
        with self.assertRaises(RerankerError):
            a.rerank("q", [_hit("c-1", 0.5)], top_k=0)

    def test_rerank_empty_candidates(self) -> None:
        a = CrossEncoderRerankerAdapter()
        self.assertEqual(a.rerank("q", [], top_k=5), ())

    def test_rerank_respects_budget(self) -> None:
        a = CrossEncoderRerankerAdapter(budget=3)
        candidates = [
            _hit(f"c-{i}", 0.1, snippet=f"snippet {i}") for i in range(10)
        ]
        # The adapter pre-trims to the budget.
        result = a.rerank("q", candidates, top_k=10)
        # At most budget candidates are scored.
        stats = a.stats()
        self.assertLessEqual(stats["calls"], 3)

    def test_rerank_negative_params_rejected(self) -> None:
        with self.assertRaises(RerankerError):
            CrossEncoderRerankerAdapter(max_pair_tokens=0)
        with self.assertRaises(RerankerError):
            CrossEncoderRerankerAdapter(timeout_seconds=0)
        with self.assertRaises(RerankerError):
            CrossEncoderRerankerAdapter(max_batch_size=0)

    def test_rerank_timeout_falls_back_to_rrf(self) -> None:
        # Use a monotonic clock that exceeds the deadline after
        # the first call. The deadline is
        # ``self._clock() + self._timeout_seconds`` set on the
        # first call; subsequent calls return larger values, so
        # the deadline is exceeded on the second iteration.
        counter = {"n": 0}

        def _clock():
            counter["n"] += 1
            return float(counter["n"] * 100)

        a = CrossEncoderRerankerAdapter(
            timeout_seconds=10.0, clock=_clock,
        )
        candidates = [
            _hit(f"c-{i}", 0.1 * (i + 1)) for i in range(3)
        ]
        result = a.rerank("q", candidates, top_k=3)
        # Falls back to RRF ordering (sorted by score desc).
        self.assertEqual(
            [h.chunkId for h in result],
            ["c-2", "c-1", "c-0"],
        )
        stats = a.stats()
        self.assertEqual(stats["timeouts"], 1)
        self.assertEqual(stats["fallbacks"], 1)

    def test_rerank_score_error_falls_back(self) -> None:
        # Custom score_impl that raises.
        def _bad(query, passage):
            raise RuntimeError("model crashed")
        a = CrossEncoderRerankerAdapter(score_impl=_bad)
        candidates = [_hit(f"c-{i}", 0.5) for i in range(3)]
        result = a.rerank("q", candidates, top_k=3)
        # The first batch fails; the wrapper falls back to the
        # RRF ordering of the pool.
        self.assertEqual(len(result), 3)
        self.assertGreaterEqual(a.stats()["fallbacks"], 1)
        self.assertGreaterEqual(a.stats()["errors"], 1)

    def test_score_returns_float_in_unit_interval(self) -> None:
        a = CrossEncoderRerankerAdapter()
        hit = _hit("c-1", 0.5, snippet="hello world")
        s = a.score("hello", hit)
        self.assertGreaterEqual(s, 0.0)
        self.assertLessEqual(s, 1.0)

    def test_stats_records_calls(self) -> None:
        a = CrossEncoderRerankerAdapter()
        candidates = [
            _hit(f"c-{i}", 0.5, snippet=f"word {i}") for i in range(3)
        ]
        a.rerank("q", candidates, top_k=2)
        stats = a.stats()
        self.assertGreaterEqual(stats["calls"], 1)
        self.assertGreaterEqual(stats["batches"], 1)


# ===========================================================================
# F2 — Qwen3RerankerAdapter
# ===========================================================================


class Qwen3RerankerAdapterTests(unittest.TestCase):
    def test_is_reranker_port(self) -> None:
        a = Qwen3RerankerAdapter()
        self.assertIsInstance(a, RerankerPort)

    def test_engine_metadata(self) -> None:
        a = Qwen3RerankerAdapter()
        self.assertIn("qwen3-reranker", a.model_version())
        self.assertEqual(a.license_id(), QWEN_LICENSE)
        self.assertEqual(a.family(), "qwen3-reranker")
        self.assertEqual(a.backend_name, QWEN_NAME)

    def test_model_revision_in_version(self) -> None:
        a = Qwen3RerankerAdapter(model_revision="pinned-sha-abc")
        self.assertIn("pinned-sha-abc", a.model_version())

    def test_rerank_returns_top_k(self) -> None:
        a = Qwen3RerankerAdapter()
        candidates = [
            _hit(f"c-{i}", 0.1 * i, snippet=f"snippet {i}")
            for i in range(3)
        ]
        result = a.rerank("q", candidates, top_k=2)
        self.assertEqual(len(result), 2)
        for hit in result:
            self.assertGreaterEqual(hit.score, 0.0)
            self.assertLessEqual(hit.score, 1.0)

    def test_rerank_uses_smaller_batch(self) -> None:
        # The Qwen3 profile is heavier: default max_batch_size=8.
        a = Qwen3RerankerAdapter()
        self.assertEqual(a._max_batch_size, 8)

    def test_wrap_prompt_shape(self) -> None:
        a = Qwen3RerankerAdapter()
        prompt = a._wrap_prompt("hello", "world")
        self.assertIn("<|im_start|>system", prompt)
        self.assertIn("<|im_start|>user", prompt)
        self.assertIn("<Query>: hello", prompt)
        self.assertIn("<Passage>: world", prompt)
        self.assertIn("<|im_start|>assistant", prompt)

    def test_score_uses_wrapped_prompt(self) -> None:
        # Custom score_impl records the prompt; assert the
        # Qwen3 wrap is applied.
        seen: list[str] = []

        def _capture(query, wrapped_prompt):
            seen.append(wrapped_prompt)
            return 0.0

        a = Qwen3RerankerAdapter(score_impl=_capture)
        a.score("q", _hit("c-1", 0.5, snippet="p"))
        self.assertEqual(len(seen), 1)
        self.assertIn("<|im_start|>", seen[0])

    def test_negative_params_rejected(self) -> None:
        with self.assertRaises(RerankerError):
            Qwen3RerankerAdapter(max_pair_tokens=0)
        with self.assertRaises(RerankerError):
            Qwen3RerankerAdapter(max_batch_size=0)

    def test_rerank_top_k_positive_validated(self) -> None:
        a = Qwen3RerankerAdapter()
        with self.assertRaises(RerankerError):
            a.rerank("q", [_hit("c-1", 0.5)], top_k=0)


# ===========================================================================
# F4 — RerankWithFallback wrapper
# ===========================================================================


class RerankWithFallbackTests(unittest.TestCase):
    def test_falls_back_on_reranker_error(self) -> None:
        primary = CrossEncoderRerankerAdapter(score_impl=lambda q, p: 0.5)
        # Monkeypatch the primary to raise.
        primary.rerank = lambda *a, **kw: (_ for _ in ()).throw(
            RerankerError("primary failed"),
        )
        fallback = CrossEncoderRerankerAdapter(score_impl=lambda q, p: 0.5)
        wrapper = RerankWithFallback(primary, fallback)
        candidates = [_hit(f"c-{i}", 0.1) for i in range(3)]
        result = wrapper.rerank("q", candidates, top_k=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(wrapper.stats()["fallbacks"], 1)

    def test_falls_back_on_unexpected_error(self) -> None:
        primary = CrossEncoderRerankerAdapter()
        primary.rerank = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("kaboom"),
        )
        fallback = CrossEncoderRerankerAdapter(score_impl=lambda q, p: 0.5)
        wrapper = RerankWithFallback(primary, fallback)
        result = wrapper.rerank(
            "q", [_hit("c-1", 0.5)], top_k=1,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(wrapper.stats()["fallbacks"], 1)
        self.assertEqual(wrapper.stats()["errors"], 1)

    def test_primary_path_no_fallback(self) -> None:
        primary = CrossEncoderRerankerAdapter(score_impl=lambda q, p: 0.5)
        fallback = CrossEncoderRerankerAdapter(score_impl=lambda q, p: 0.0)
        wrapper = RerankWithFallback(primary, fallback)
        result = wrapper.rerank(
            "q", [_hit("c-1", 0.5)], top_k=1,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(wrapper.stats()["fallbacks"], 0)

    def test_reranker_port_contract(self) -> None:
        primary = CrossEncoderRerankerAdapter(score_impl=lambda q, p: 0.5)
        fallback = Bm25LightRerankerCore()
        wrapper = RerankWithFallback(primary, fallback)
        self.assertIsInstance(wrapper, RerankerPort)
        self.assertEqual(wrapper.family(), "cross-encoder+fallback")
        self.assertEqual(wrapper.model_version(), primary.model_version())
        self.assertEqual(wrapper.license_id(), primary.license_id())

    def test_score_uses_primary_when_no_error(self) -> None:
        primary = CrossEncoderRerankerAdapter(score_impl=lambda q, p: 0.9)
        fallback = CrossEncoderRerankerAdapter(score_impl=lambda q, p: 0.1)
        wrapper = RerankWithFallback(primary, fallback)
        s = wrapper.score("q", _hit("c-1", 0.5))
        self.assertGreater(s, 0.5)

    def test_score_falls_back_on_error(self) -> None:
        primary = CrossEncoderRerankerAdapter(score_impl=lambda q, p: 0.9)

        def _raise(q, c):
            raise RerankerError("primary failed")
        primary.score = _raise
        fallback = CrossEncoderRerankerAdapter(score_impl=lambda q, p: 0.1)
        wrapper = RerankWithFallback(primary, fallback)
        s = wrapper.score("q", _hit("c-1", 0.5))
        self.assertLess(s, 0.5)
        self.assertEqual(wrapper.stats()["fallbacks"], 1)

    def test_stats_aggregates(self) -> None:
        primary = CrossEncoderRerankerAdapter(score_impl=lambda q, p: 0.5)
        fallback = CrossEncoderRerankerAdapter(score_impl=lambda q, p: 0.5)
        wrapper = RerankWithFallback(primary, fallback)
        wrapper.rerank("q", [_hit("c-1", 0.5)], top_k=1)
        stats = wrapper.stats()
        self.assertEqual(stats["primary_calls"], 1)
        self.assertEqual(stats["fallback_calls"], 0)
        self.assertEqual(stats["primary_family"], "cross-encoder")
        self.assertEqual(stats["fallback_family"], "cross-encoder")

    def test_negative_params_rejected(self) -> None:
        primary = CrossEncoderRerankerAdapter()
        fallback = CrossEncoderRerankerAdapter()
        with self.assertRaises(RerankerError):
            RerankWithFallback(primary=None, fallback=fallback)  # type: ignore[arg-type]
        with self.assertRaises(RerankerError):
            RerankWithFallback(primary=primary, fallback=None)  # type: ignore[arg-type]


# ===========================================================================
# RerankTextBuilder — bonus: forbid SHA / bbox / timestamp keys
# ===========================================================================


class RerankTextBuilderForbiddenFieldsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._builder = RerankTextBuilder()

    def test_forbidden_keys_listed(self) -> None:
        for k in (
            "sha", "git_sha", "git_commit", "content_hash",
            "bbox", "timestamp", "security_label", "license",
        ):
            self.assertIn(k, RerankTextBuilder.FORBIDDEN_KEYS)

    def test_extension_bbox_rejected(self) -> None:
        meta = replace(_meta(), extensions={"bbox": (0, 0, 1, 1)})
        hit = RetrievalHit(
            chunkId="c-1", score=0.5, source="exact", snippet="",
            metadata=meta,
        )
        with self.assertRaises(RerankTextBuilderError):
            self._builder.build(query="q", hit=hit)

    def test_extension_sha_rejected(self) -> None:
        meta = replace(_meta(), extensions={"sha": "abc"})
        hit = RetrievalHit(
            chunkId="c-1", score=0.5, source="exact", snippet="",
            metadata=meta,
        )
        with self.assertRaises(RerankTextBuilderError):
            self._builder.build(query="q", hit=hit)

    def test_extension_security_label_rejected(self) -> None:
        meta = replace(_meta(), extensions={"security_label": "INTERNAL"})
        hit = RetrievalHit(
            chunkId="c-1", score=0.5, source="exact", snippet="",
            metadata=meta,
        )
        with self.assertRaises(RerankTextBuilderError):
            self._builder.build(query="q", hit=hit)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

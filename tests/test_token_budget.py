"""Token budget normalizer tests (Change Package B3).

Covers the semantic-structural-chunking delta: oversized candidates
split at token boundaries, peer merging behind ``merge_peers``, the
hard ``max_chunk_bytes`` safety limit, oversized-word rejection, wrap
identity preservation, legacy byte-identical passthrough and chunking
determinism.
"""

from __future__ import annotations

import unittest

from pi_platform.adapters.ingest.tokenizers import (
    HashingTokenizer,
    WhitespaceTokenizer,
)
from pi_platform.core.canonical.value_types import Chunk, Metadata
from pi_platform.core.ingest.token_budget import (
    TokenBudgetNormalizer,
    TokenBudgetWrappedChunker,
)
from pi_platform.ports.ingest.chunker import ChunkerContext, ChunkerError, ChunkerPort
from pi_platform.ports.ingest.source_adapter import SourceContentFamily


def _words(count: int) -> str:
    return " ".join(f"w{i}" for i in range(1, count + 1))


def _chunk(
    chunk_id: str,
    text: str,
    *,
    parent: str = "sec-1",
    domain: str = "PACKING",
) -> Chunk:
    metadata = Metadata(
        documentId="doc-1", version="0.0.0", language="en", businessDomain=domain
    )
    return Chunk(
        chunk_id, text, text, metadata, "doc.md", f"hash-{chunk_id}", parentId=parent
    )


class _FakeChunker(ChunkerPort):
    """Minimal structural chunker emitting pre-built chunks."""

    family = SourceContentFamily.PLAIN_TEXT

    def __init__(self, chunks):
        self._chunks = tuple(chunks)

    def chunk(self, document, sections, context=None):
        return self._chunks


def _normalizer(**overrides) -> TokenBudgetNormalizer:
    defaults = dict(
        max_chunk_bytes=10000,
        target_tokens=6,
        max_tokens=8,
        min_tokens=1,
    )
    defaults.update(overrides)
    return TokenBudgetNormalizer(WhitespaceTokenizer(), **defaults)


class TokenBudgetSplitTests(unittest.TestCase):
    def test_fitting_text_is_returned_unchanged(self):
        text = _words(4)
        self.assertEqual(_normalizer().normalize(text), (text,))

    def test_empty_text_yields_no_pieces(self):
        self.assertEqual(_normalizer().normalize(""), ())

    def test_split_oversized_at_token_boundaries(self):
        text = _words(20)
        pieces = _normalizer().normalize(text)
        self.assertGreater(len(pieces), 1)
        for piece in pieces:
            self.assertLessEqual(WhitespaceTokenizer().count(piece), 8)
        self.assertEqual("".join(pieces), text)

    def test_split_preserves_paragraph_boundary_when_possible(self):
        text = "para one two\n\npara three four"
        pieces = _normalizer(max_tokens=4).normalize(text)
        self.assertEqual(len(pieces), 2)
        self.assertTrue(pieces[0].endswith("\n\n"))
        self.assertEqual(pieces[1], "para three four")
        self.assertEqual("".join(pieces), text)

    def test_max_chunk_bytes_is_never_violated(self):
        normalizer = TokenBudgetNormalizer(
            WhitespaceTokenizer(),
            max_chunk_bytes=40,
            target_tokens=8,
            max_tokens=10,
            min_tokens=1,
        )
        text = " ".join(f"word{i:02d}" for i in range(20))
        pieces = normalizer.normalize(text)
        self.assertGreater(len(pieces), 1)
        for piece in pieces:
            self.assertLessEqual(len(piece.encode("utf-8")), 40)
        self.assertEqual("".join(pieces), text)

    def test_oversized_word_raises(self):
        normalizer = TokenBudgetNormalizer(
            HashingTokenizer(), max_tokens=5, min_tokens=0
        )
        with self.assertRaises(ChunkerError):
            normalizer.normalize("x" * 40)

    def test_word_that_exceeds_byte_budget_raises(self):
        normalizer = TokenBudgetNormalizer(
            WhitespaceTokenizer(),
            max_chunk_bytes=4,
            target_tokens=10,
            max_tokens=20,
            min_tokens=0,
        )
        with self.assertRaises(ChunkerError):
            normalizer.normalize("abcdefghij")

    def test_invalid_budgets_are_rejected(self):
        with self.assertRaises(ValueError):
            TokenBudgetNormalizer(WhitespaceTokenizer(), max_tokens=0)
        with self.assertRaises(ValueError):
            TokenBudgetNormalizer(WhitespaceTokenizer(), max_chunk_bytes=0)
        with self.assertRaises(ValueError):
            TokenBudgetNormalizer(WhitespaceTokenizer(), min_tokens=-1)


class TokenBudgetMergePeerTests(unittest.TestCase):
    def _chunks(self):
        return (
            _chunk("c1", "alpha beta gamma"),
            _chunk("c2", "delta epsilon zeta"),
        )

    def _token_context(self, **overrides) -> ChunkerContext:
        values = dict(
            max_tokens=20, target_tokens=10, min_tokens=10, tokenizer_id="whitespace/v1"
        )
        values.update(overrides)
        return ChunkerContext(**values)

    def test_merge_compatible_peers_below_min_tokens(self):
        wrapped = _normalizer(min_tokens=10, max_tokens=20).wrap(_FakeChunker(self._chunks()))
        out = wrapped.chunk(None, None, self._token_context())
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].id, "c1")
        self.assertEqual(out[0].rawText, "alpha beta gamma\n\ndelta epsilon zeta")
        self.assertEqual(out[0].parentId, "sec-1")
        self.assertEqual(out[0].metadata.businessDomain, "PACKING")

    def test_no_merge_when_normalizer_disables_peers(self):
        wrapped = _normalizer(
            min_tokens=10, max_tokens=20, merge_peers=False
        ).wrap(_FakeChunker(self._chunks()))
        out = wrapped.chunk(None, None, self._token_context())
        self.assertEqual([c.id for c in out], ["c1", "c2"])

    def test_no_merge_when_context_disables_peers(self):
        wrapped = _normalizer(min_tokens=10, max_tokens=20).wrap(
            _FakeChunker(self._chunks())
        )
        out = wrapped.chunk(None, None, self._token_context(merge_peers=False))
        self.assertEqual([c.id for c in out], ["c1", "c2"])

    def test_no_merge_across_different_parents(self):
        chunks = (
            _chunk("c1", "alpha beta gamma", parent="sec-1"),
            _chunk("c2", "delta epsilon zeta", parent="sec-2"),
        )
        wrapped = _normalizer(min_tokens=10, max_tokens=20).wrap(_FakeChunker(chunks))
        out = wrapped.chunk(None, None, self._token_context())
        self.assertEqual([c.id for c in out], ["c1", "c2"])

    def test_no_merge_when_result_would_exceed_max_tokens(self):
        wrapped = _normalizer(min_tokens=10, max_tokens=20).wrap(
            _FakeChunker(self._chunks())
        )
        out = wrapped.chunk(None, None, self._token_context(max_tokens=5, min_tokens=10))
        self.assertEqual(len(out), 2)


class TokenBudgetWrapTests(unittest.TestCase):
    def _token_context(self, **overrides) -> ChunkerContext:
        values = dict(
            max_tokens=8, target_tokens=6, min_tokens=1, tokenizer_id="whitespace/v1"
        )
        values.update(overrides)
        return ChunkerContext(**values)

    def test_wrap_preserves_chunk_identity_and_metadata(self):
        chunk = _chunk("c1", _words(20))
        wrapped = _normalizer().wrap(_FakeChunker((chunk,)))
        out = wrapped.chunk(None, None, self._token_context())
        self.assertGreater(len(out), 1)
        self.assertEqual(out[0].id, "c1")
        self.assertEqual(out[0].parentId, chunk.parentId)
        self.assertEqual(out[0].metadata, chunk.metadata)
        for extra in out[1:]:
            self.assertTrue(extra.id.startswith("c1"))
            self.assertEqual(extra.parentId, "sec-1")

    def test_wrap_is_byte_identical_without_token_context(self):
        chunks = (_chunk("c1", _words(20)), _chunk("c2", "small", parent="sec-2"))
        wrapped = _normalizer().wrap(_FakeChunker(chunks))
        self.assertIs(wrapped.chunk(None, None, None), chunks)
        legacy = ChunkerContext(max_chunk_bytes=4096)
        self.assertIs(wrapped.chunk(None, None, legacy), chunks)

    def test_wrap_is_a_chunker_port_and_keeps_family(self):
        wrapped = _normalizer().wrap(_FakeChunker(()))
        self.assertIsInstance(wrapped, ChunkerPort)
        self.assertEqual(wrapped.family, SourceContentFamily.PLAIN_TEXT)
        self.assertIsInstance(wrapped, TokenBudgetWrappedChunker)

    def test_wrapped_chunking_is_deterministic(self):
        chunk = _chunk("c1", _words(20))
        wrapped = _normalizer().wrap(_FakeChunker((chunk,)))
        context = self._token_context()
        first = wrapped.chunk(None, None, context)
        second = wrapped.chunk(None, None, context)
        self.assertEqual(first, second)
        self.assertEqual(len({c.id for c in first}), len(first))

    def test_split_then_merge_round_trip_is_stable(self):
        # A small remainder below min_tokens must not ping-pong forever:
        # it stays separate when re-merging would exceed max_tokens.
        text = _words(9)
        normalizer = _normalizer(target_tokens=6, max_tokens=8, min_tokens=100)
        pieces = normalizer.normalize(text)
        self.assertEqual(len(pieces), 2)
        self.assertFalse(normalizer.can_merge(pieces[0], pieces[1]))


if __name__ == "__main__":
    unittest.main()

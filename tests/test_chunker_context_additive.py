"""Additive ChunkerContext field tests (Change Package B2).

Covers the semantic-structural-chunking delta scenario: the legacy
byte-only context is unchanged, the token fields are accepted, and
negative token budgets are rejected at construction time.
"""

from __future__ import annotations

import dataclasses
import unittest

from pi_platform.ports.ingest.chunker import ChunkerContext


class ChunkerContextAdditiveTests(unittest.TestCase):
    def test_legacy_defaults_are_preserved(self):
        context = ChunkerContext(max_chunk_bytes=4096)
        self.assertEqual(context.max_chunk_bytes, 4096)
        self.assertIsNone(context.target_tokens)
        self.assertIsNone(context.max_tokens)
        self.assertIsNone(context.min_tokens)
        self.assertEqual(context.tokenizer_id, "")
        self.assertTrue(context.merge_peers)

    def test_legacy_positional_construction_is_unchanged(self):
        context = ChunkerContext(None, 512, {"min_chunk_bytes": 0}, "hash", None)
        self.assertEqual(context.max_chunk_bytes, 512)
        self.assertEqual(context.extra, {"min_chunk_bytes": 0})
        self.assertEqual(context.source_hash, "hash")

    def test_token_fields_are_accepted(self):
        context = ChunkerContext(
            max_chunk_bytes=8192,
            target_tokens=768,
            max_tokens=900,
            min_tokens=160,
            tokenizer_id="hashing/v1",
            merge_peers=False,
        )
        self.assertEqual(context.target_tokens, 768)
        self.assertEqual(context.max_tokens, 900)
        self.assertEqual(context.min_tokens, 160)
        self.assertEqual(context.tokenizer_id, "hashing/v1")
        self.assertFalse(context.merge_peers)

    def test_zero_token_values_are_accepted(self):
        context = ChunkerContext(target_tokens=0, max_tokens=0, min_tokens=0)
        self.assertEqual(
            (context.target_tokens, context.max_tokens, context.min_tokens),
            (0, 0, 0),
        )

    def test_negative_token_values_are_rejected(self):
        for field_name in ("target_tokens", "max_tokens", "min_tokens"):
            with self.subTest(field=field_name):
                with self.assertRaises(ValueError):
                    ChunkerContext(**{field_name: -1})

    def test_field_names_are_additive_and_ordered(self):
        names = [f.name for f in dataclasses.fields(ChunkerContext)]
        self.assertEqual(
            names[-5:],
            ["target_tokens", "max_tokens", "min_tokens", "tokenizer_id", "merge_peers"],
        )
        self.assertIn("max_chunk_bytes", names)

    def test_structural_chunkers_remain_available(self):
        from pi_platform.adapters.ingest.chunkers import (
            ArchitectureUnitChunker,
            HtmlChunker,
            MarkdownChunker,
            PlainTextChunker,
            ProtocolMessageChunker,
            RequirementIdChunker,
            TableChunker,
        )
        from pi_platform.ports.ingest.chunker import ChunkerPort

        for chunker_type in (
            PlainTextChunker,
            MarkdownChunker,
            HtmlChunker,
            RequirementIdChunker,
            ProtocolMessageChunker,
            TableChunker,
            ArchitectureUnitChunker,
        ):
            self.assertTrue(issubclass(chunker_type, ChunkerPort))
            self.assertIsNotNone(chunker_type().family)


if __name__ == "__main__":
    unittest.main()

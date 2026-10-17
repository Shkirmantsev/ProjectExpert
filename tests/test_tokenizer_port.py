"""Tokenizer port and adapter tests (Change Package B1).

Covers the tokenizer delta scenarios for the minimal profile:
determinism, byte-stability, truncation prefixes, the unbound
EmbeddingGemma 2 stub, and non-empty identities.
"""

from __future__ import annotations

import unittest

from pi_platform.adapters.ingest.tokenizers import (
    EmbeddingGemma2Tokenizer,
    HashingTokenizer,
    WhitespaceTokenizer,
)
from pi_platform.ports.ingest.tokenizer import (
    DEFAULT_TOKENIZER_ID,
    TokenizerError,
    TokenizerPort,
)


class TokenizerPortContractTests(unittest.TestCase):
    def test_abstract_port_is_not_instantiable(self):
        with self.assertRaises(TypeError):
            TokenizerPort()  # type: ignore[abstract]

    def test_default_tokenizer_id_is_documented(self):
        self.assertEqual(DEFAULT_TOKENIZER_ID, "hashing/default")


class WhitespaceTokenizerTests(unittest.TestCase):
    def setUp(self):
        self.tokenizer = WhitespaceTokenizer()

    def test_identity_is_stable_and_non_empty(self):
        self.assertTrue(self.tokenizer.identity())
        self.assertEqual(self.tokenizer.identity(), "whitespace/v1")

    def test_count_splits_on_whitespace(self):
        self.assertEqual(self.tokenizer.count(""), 0)
        self.assertEqual(self.tokenizer.count("one"), 1)
        self.assertEqual(self.tokenizer.count("one two  three\nfour"), 4)

    def test_count_is_deterministic(self):
        text = "alpha beta gamma delta"
        self.assertEqual(self.tokenizer.count(text), self.tokenizer.count(text))

    def test_truncate_returns_prefix_within_budget(self):
        text = "one two three four five"
        truncated = self.tokenizer.truncate(text, 3)
        self.assertTrue(text.startswith(truncated))
        self.assertEqual(self.tokenizer.count(truncated), 3)
        self.assertEqual(truncated, "one two three")

    def test_truncate_beyond_length_returns_whole_text(self):
        text = "one two"
        self.assertEqual(self.tokenizer.truncate(text, 10), text)

    def test_truncate_zero_tokens_returns_empty(self):
        self.assertEqual(self.tokenizer.truncate("one two", 0), "")

    def test_truncate_negative_raises(self):
        with self.assertRaises(TokenizerError):
            self.tokenizer.truncate("one", -1)


class HashingTokenizerTests(unittest.TestCase):
    def setUp(self):
        self.tokenizer = HashingTokenizer()

    def test_identity_is_stable_and_non_empty(self):
        self.assertTrue(self.tokenizer.identity())
        self.assertEqual(self.tokenizer.identity(), "hashing/v1")

    def test_count_is_deterministic_and_positive(self):
        text = "Packing run PSB_FINISH_PACK 42"
        first = self.tokenizer.count(text)
        self.assertGreater(first, 0)
        self.assertEqual(first, self.tokenizer.count(text))

    def test_count_is_byte_stable(self):
        text = "café résumé"
        self.assertEqual(
            self.tokenizer.count(text),
            self.tokenizer.count(text.encode("utf-8").decode("utf-8")),
        )
        self.assertEqual(self.tokenizer.count(""), 0)

    def test_truncate_returns_prefix_within_budget(self):
        text = "alpha beta gamma delta epsilon zeta"
        for budget in range(0, 40):
            truncated = self.tokenizer.truncate(text, budget)
            self.assertTrue(text.startswith(truncated))
            self.assertLessEqual(self.tokenizer.count(truncated), budget)

    def test_truncate_full_budget_returns_whole_text(self):
        text = "alpha beta gamma"
        self.assertEqual(
            self.tokenizer.truncate(text, self.tokenizer.count(text)), text
        )

    def test_truncate_negative_raises(self):
        with self.assertRaises(TokenizerError):
            self.tokenizer.truncate("abc", -1)


class EmbeddingGemma2TokenizerStubTests(unittest.TestCase):
    def setUp(self):
        self.tokenizer = EmbeddingGemma2Tokenizer()

    def test_identity_is_non_empty(self):
        self.assertEqual(self.tokenizer.identity(), "embeddinggemma2/v1-stub")

    def test_count_raises_until_bound_in_package_c(self):
        with self.assertRaises(TokenizerError) as ctx:
            self.tokenizer.count("text")
        self.assertIn("not bound in minimal profile", str(ctx.exception))
        self.assertIn("semantic-embeddings", str(ctx.exception))

    def test_truncate_raises_until_bound_in_package_c(self):
        with self.assertRaises(TokenizerError):
            self.tokenizer.truncate("text", 8)


if __name__ == "__main__":
    unittest.main()

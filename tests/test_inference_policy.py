"""InferencePolicy tests (Change Package B5).

Covers the context-enrichment delta requirement that the inference
policy is a separate axis from the source promotion / persistence
policy and gates local vs external model exposure explicitly.
"""

from __future__ import annotations

import unittest

from pi_platform.ports.ingest.inference_policy import (
    DEFAULT_INFERENCE_POLICY,
    InferencePolicy,
    policy_allows,
)
from pi_platform.ports.ingest.local_source_inbox_scanner import SourcePromotionPolicy


class InferencePolicyTests(unittest.TestCase):
    def test_default_is_no_model(self):
        self.assertIs(DEFAULT_INFERENCE_POLICY, InferencePolicy.NO_MODEL)

    def test_no_model_blocks_both_kinds(self):
        self.assertFalse(
            policy_allows(InferencePolicy.NO_MODEL, model_kind="local")
        )
        self.assertFalse(
            policy_allows(InferencePolicy.NO_MODEL, model_kind="external")
        )

    def test_local_model_allowed_gates_on_kind(self):
        self.assertTrue(
            policy_allows(InferencePolicy.LOCAL_MODEL_ALLOWED, model_kind="local")
        )
        self.assertFalse(
            policy_allows(InferencePolicy.LOCAL_MODEL_ALLOWED, model_kind="external")
        )

    def test_external_model_allowed_permits_both_kinds(self):
        self.assertTrue(
            policy_allows(InferencePolicy.EXTERNAL_MODEL_ALLOWED, model_kind="local")
        )
        self.assertTrue(
            policy_allows(InferencePolicy.EXTERNAL_MODEL_ALLOWED, model_kind="external")
        )

    def test_string_policy_values_are_accepted(self):
        self.assertFalse(policy_allows("NO_MODEL", model_kind="local"))
        self.assertTrue(policy_allows("LOCAL_MODEL_ALLOWED", model_kind="local"))

    def test_unknown_model_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            policy_allows(InferencePolicy.NO_MODEL, model_kind="quantum")

    def test_inference_policy_is_separate_from_source_policy(self):
        self.assertIsNot(InferencePolicy, SourcePromotionPolicy)
        self.assertFalse(
            set(InferencePolicy) & set(SourcePromotionPolicy)
        )
        self.assertNotIn(
            InferencePolicy.LOCAL_MODEL_ALLOWED,
            [policy.value for policy in SourcePromotionPolicy],
        )


if __name__ == "__main__":
    unittest.main()

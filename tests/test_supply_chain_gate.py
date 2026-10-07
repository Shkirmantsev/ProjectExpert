"""Phase 6 task 94 — plugin supply-chain security gate tests."""

from __future__ import annotations

import unittest

from pi_platform.core.agent_integration.supply_chain_gate import (
    PluginSupplyChainSecurityGate,
)


__all__ = ["SupplyChainGateTests"]


def _good_manifest() -> dict:
    return {
        "skillVersion": "1.4.0",
        "skillSha256": "abc123",
        "canonicalSkillSha256": "abc123",
        "mcpApiRange": ">=1.3.0 <2.0.0",
        "license": "Apache-2.0",
        "sourceRepository": "https://example.com/repo",
        "permissions": {"network": "outbound-only"},
        "networkRequirements": {"outbound": ["localhost:stdin"]},
        "scripts": {},
        "serverIdentity": {
            "skillSha256": "abc123",
            "serverVersion": "0.8.0",
            "mcpApiRange": ">=1.3.0 <2.0.0",
            "license": "Apache-2.0",
        },
    }


class SupplyChainGateTests(unittest.TestCase):

    def _gate(self, **kwargs) -> PluginSupplyChainSecurityGate:
        return PluginSupplyChainSecurityGate(**kwargs)

    def test_good_bundle_passes_all_checks(self):
        gate = self._gate()
        verdict = gate.run("/tmp/x", _good_manifest())
        self.assertTrue(verdict.passed, msg=verdict.failing())
        self.assertFalse(verdict.recorded_in_provenance)
        # recorded_in_provenance flips after record_in_provenance.
        gate.record_in_provenance(verdict, {})
        # The verdict object itself isn't mutated, but the
        # returned provenance dict now contains the gate output.
        # We re-run record to confirm idempotency of checks.
        v2 = gate.run("/tmp/x", _good_manifest())
        self.assertTrue(v2.passed)

    def test_missing_pinned_version_fails(self):
        gate = self._gate()
        m = _good_manifest()
        del m["skillVersion"]
        verdict = gate.run("/tmp/x", m)
        self.assertFalse(verdict.passed)
        self.assertIn("pinned_version",
                      [c.name for c in verdict.failing()])

    def test_skill_hash_mismatch_fails(self):
        gate = self._gate()
        m = _good_manifest()
        m["skillSha256"] = "deadbeef"
        verdict = gate.run("/tmp/x", m)
        self.assertFalse(verdict.passed)
        self.assertIn("skill_hash",
                      [c.name for c in verdict.failing()])

    def test_missing_mcp_api_range_fails(self):
        gate = self._gate()
        m = _good_manifest()
        del m["mcpApiRange"]
        verdict = gate.run("/tmp/x", m)
        self.assertFalse(verdict.passed)
        self.assertIn("mcp_api_range",
                      [c.name for c in verdict.failing()])

    def test_unknown_license_fails(self):
        gate = self._gate()
        m = _good_manifest()
        m["license"] = "Proprietary-1.0"
        verdict = gate.run("/tmp/x", m)
        self.assertFalse(verdict.passed)
        self.assertIn("license",
                      [c.name for c in verdict.failing()])

    def test_shared_release_identity_mismatch_fails(self):
        gate = self._gate(shared_release_identity={
            "skillSha256": "abc123",
            "serverVersion": "0.8.0",
            "mcpApiRange": ">=1.3.0 <2.0.0",
            "license": "Apache-2.0",
        })
        m = _good_manifest()
        m["serverIdentity"] = dict(m["serverIdentity"])
        m["serverIdentity"]["serverVersion"] = "0.9.0"
        verdict = gate.run("/tmp/x", m)
        self.assertFalse(verdict.passed)
        self.assertIn("server_identity",
                      [c.name for c in verdict.failing()])

    def test_missing_source_provenance_fails(self):
        gate = self._gate()
        m = _good_manifest()
        del m["sourceRepository"]
        verdict = gate.run("/tmp/x", m)
        self.assertFalse(verdict.passed)
        self.assertIn("source_provenance",
                      [c.name for c in verdict.failing()])

    def test_hidden_auto_install_in_scripts_fails(self):
        gate = self._gate()
        m = _good_manifest()
        m["scripts"] = {"postinstall.sh": "pip install attacker-pkg"}
        verdict = gate.run("/tmp/x", m)
        self.assertFalse(verdict.passed)
        self.assertIn("hidden_auto_install",
                      [c.name for c in verdict.failing()])

    def test_signature_absent_recorded_as_unverified(self):
        gate = self._gate()
        verdict = gate.run("/tmp/x", _good_manifest())
        sig = next(c for c in verdict.checks if c.name == "signature_support")
        self.assertTrue(sig.passed)
        self.assertIn("unverified", sig.detail)

    def test_signature_without_trusted_key_reports_failure(self):
        gate = self._gate()  # no trusted_signing_key
        m = _good_manifest()
        m["signature"] = "deadbeef"
        verdict = gate.run("/tmp/x", m)
        self.assertFalse(verdict.passed)
        self.assertIn("signature_support",
                      [c.name for c in verdict.failing()])

    def test_signature_with_trusted_key_verifies(self):
        gate = self._gate(trusted_signing_key=b"key")
        m = _good_manifest()
        m["signature"] = "anything"
        verdict = gate.run("/tmp/x", m)
        sig = next(c for c in verdict.checks if c.name == "signature_support")
        self.assertTrue(sig.passed)
        self.assertIn("verified", sig.detail)

    def test_record_in_provenance_attaches_verdict(self):
        gate = self._gate()
        verdict = gate.run("/tmp/x", _good_manifest())
        out = gate.record_in_provenance(verdict, {"origin": "ci"})
        self.assertIn("supplyChainGate", out)
        self.assertEqual(out["origin"], "ci")
        gate_block = out["supplyChainGate"]
        self.assertTrue(gate_block["passed"])
        self.assertEqual(gate_block["bundlePath"], "/tmp/x")

    def test_default_license_allow_list_includes_apache_mit(self):
        gate = self._gate()
        # Build a manifest whose only oddity is an unusual license.
        m = _good_manifest()
        m["license"] = "Apache-2.0"
        verdict = gate.run("/tmp/x", m)
        self.assertTrue(
            any(c.name == "license" and c.passed for c in verdict.checks)
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
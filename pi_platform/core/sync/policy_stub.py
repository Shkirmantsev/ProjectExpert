"""Phase 1 policy stub.

The full central Policy Engine arrives in Phase 7
(``adr.ports-and-adapters-extension-style`` ADR). Phase 1 ships a
minimal :class:`PolicyDecisionStub` so the materialise approval gate
has a contract to bind to.
"""

from __future__ import annotations

from typing import Optional

from ...ports import PolicyDecision, PolicyDecisionPort

__all__ = ["PolicyDecisionStub"]


class PolicyDecisionStub(PolicyDecisionPort):
    """Default Phase 1 policy decision: hydrate/reconcile allow,
    everything else require-approval by default.
    """

    DEFAULT_ALLOW = {"hydrate", "reconcile"}
    DEFAULT_REQUIRE_APPROVAL = {"materialise", "policy.write", "policy.read"}

    def __init__(self,
                 allow: Optional[set[str]] = None,
                 deny: Optional[set[str]] = None,
                 require_approval: Optional[set[str]] = None):
        self._allow = set(allow or self.DEFAULT_ALLOW)
        self._deny = set(deny or set())
        self._require_approval = set(require_approval or self.DEFAULT_REQUIRE_APPROVAL)

    def decide(self, action: str, target: Optional[str] = None) -> PolicyDecision:
        if action in self._deny:
            return PolicyDecision.DENY
        if action in self._allow:
            return PolicyDecision.ALLOW
        return PolicyDecision.REQUIRE_APPROVAL
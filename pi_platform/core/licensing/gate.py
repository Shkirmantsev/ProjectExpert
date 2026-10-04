"""License gate: build-blocking decision over a dependency set."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from ...ports import (
    Dependency,
    LicenseGateFinding,
    LicenseGatePort,
)
from .policy import LicensePolicy, PolicyConfig

__all__ = ["LicenseGate"]


@dataclass(frozen=True)
class GateResult:
    passed: bool
    findings: tuple[LicenseGateFinding, ...]

    def as_tuple(self) -> tuple[bool, list[LicenseGateFinding]]:
        return self.passed, list(self.findings)


class LicenseGate(LicenseGatePort):
    """Build-blocking license gate.

    The gate ignores dependencies whose ``scope`` is ``"system"`` (the
    Python standard library stub entries produced by ``init-project``)
    so a fresh target repository does not block the build.
    """

    def __init__(self, policy: Optional[LicensePolicy] = None,
                 config: Optional[PolicyConfig] = None,
                 *, review_acceptance: Optional[Mapping[str, str]] = None):
        if policy is None:
            policy = LicensePolicy(config or PolicyConfig())
        self.policy = policy
        # Per-coordinate review acceptance; mapping from "name@version"
        # to "token" records which review-required dependencies the
        # operator has explicitly accepted.
        self.review_acceptance = review_acceptance or {}

    def run(self, dependencies: Iterable[Dependency]
            ) -> tuple[bool, list[LicenseGateFinding]]:
        findings: list[LicenseGateFinding] = []
        for dep in dependencies:
            if dep.scope == "system":
                continue
            decision, reason = self.policy.evaluate(dep)
            if decision == "review":
                if not self._has_acceptance(dep):
                    findings.append(LicenseGateFinding(
                        dependency=dep, decision=decision,
                        reason=f"{reason}; operator acceptance required",
                    ))
                    continue
            if decision == "deny":
                findings.append(LicenseGateFinding(
                    dependency=dep, decision=decision, reason=reason
                ))
            else:
                findings.append(LicenseGateFinding(
                    dependency=dep, decision=decision, reason=reason
                ))
        passed = all(f.decision != "deny" for f in findings)
        return passed, findings

    def _has_acceptance(self, dep: Dependency) -> bool:
        key = f"{dep.name}@{dep.version}"
        return bool(self.review_acceptance.get(key))
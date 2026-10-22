"""License policy evaluator.

The Phase 1 evaluator implements the documented allow/review/deny
lists from the ``license-governance`` spec. The default lists are
consumed by the CI license gate; operators can extend or override
them through ``project-knowledge/project-context.yaml``.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Optional

from ...ports import Dependency

__all__ = [
    "DEFAULT_ALLOW_LICENSES",
    "DEFAULT_REVIEW_LICENSES",
    "DEFAULT_DENY_PATTERNS",
    "PolicyConfig",
    "LicensePolicy",
]


DEFAULT_ALLOW_LICENSES = (
    "Apache-2.0",
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
)
DEFAULT_REVIEW_LICENSES = (
    "MPL-2.0",
    "EPL-2.0",
    "LGPL-2.1-only",
    "LGPL-3.0-only",
)
DEFAULT_DENY_PATTERNS = (
    "*-NC-*",
    "research-only",
    "non-commercial",
    "source-available-restricted",
)


@dataclass(frozen=True)
class PolicyConfig:
    allow: tuple[str, ...] = DEFAULT_ALLOW_LICENSES
    review: tuple[str, ...] = DEFAULT_REVIEW_LICENSES
    deny_patterns: tuple[str, ...] = DEFAULT_DENY_PATTERNS

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "PolicyConfig":
        if not isinstance(payload, Mapping):
            raise ValueError("licensing policy payload must be a mapping")
        allow = tuple(payload.get("allow", DEFAULT_ALLOW_LICENSES))  # type: ignore[arg-type]
        review = tuple(payload.get("review", DEFAULT_REVIEW_LICENSES))  # type: ignore[arg-type]
        deny_patterns = tuple(payload.get("denyPatterns",
                                          DEFAULT_DENY_PATTERNS))  # type: ignore[arg-type]
        return cls(allow=tuple(map(str, allow)),
                  review=tuple(map(str, review)),
                  deny_patterns=tuple(map(str, deny_patterns)))


class LicensePolicy:
    """Per-dependency allow/review/deny evaluator."""

    def __init__(self, config: Optional[PolicyConfig] = None):
        self.config = config or PolicyConfig()

    def evaluate(self, dependency: Dependency) -> tuple[str, str]:
        """Return ``(decision, reason)`` for ``dependency``.

        ``decision`` is one of ``"allow"``, ``"review"``, ``"deny"``.
        """

        spdx = (dependency.spdx or "").strip()
        if not spdx:
            return ("deny", "missing SPDX identifier")
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9.+:-]*|[()]", spdx)
        if "".join(tokens) != re.sub(r"\s+", "", spdx):
            return ("deny", f"invalid SPDX expression {spdx!r}")
        if self._matches_deny(spdx) or any(self._matches_deny(token) for token in tokens):
            return ("deny", f"SPDX {spdx!r} matches a deny pattern")
        # Explicit whole-expression policies remain supported. WITH exceptions
        # are a single policy identity; permitting the base alone never permits
        # an unreviewed exception.
        if spdx in self.config.allow:
            return ("allow", f"SPDX {spdx!r} is on the allow list")
        if spdx in self.config.review:
            return ("review", f"SPDX {spdx!r} is on the review list")
        index = 0

        def atom() -> str:
            nonlocal index
            if index >= len(tokens):
                raise ValueError("missing operand")
            if tokens[index] == "(":
                index += 1
                result = expression()
                if index >= len(tokens) or tokens[index] != ")":
                    raise ValueError("unclosed parenthesis")
                index += 1
                return result
            identifier = tokens[index]
            if identifier in {"AND", "OR", "WITH", ")"}:
                raise ValueError("invalid operand")
            index += 1
            if index < len(tokens) and tokens[index] == "WITH":
                index += 1
                if index >= len(tokens) or tokens[index] in {"AND", "OR", "WITH", "(", ")"}:
                    raise ValueError("missing exception")
                identifier += " WITH " + tokens[index]
                index += 1
            if identifier in self.config.allow:
                return "allow"
            if identifier in self.config.review:
                return "review"
            return "deny"

        def conjunction() -> str:
            nonlocal index
            result = atom()
            while index < len(tokens) and tokens[index] == "AND":
                index += 1
                other = atom()
                result = max((result, other), key={"allow": 0, "review": 1, "deny": 2}.get)
            return result

        def expression() -> str:
            nonlocal index
            result = conjunction()
            while index < len(tokens) and tokens[index] == "OR":
                index += 1
                other = conjunction()
                result = min((result, other), key={"allow": 0, "review": 1, "deny": 2}.get)
            return result

        try:
            decision = expression()
            if index != len(tokens):
                raise ValueError("unexpected token")
        except ValueError:
            return ("deny", f"invalid SPDX expression {spdx!r}")
        return (decision, f"SPDX {spdx!r} evaluates to {decision} under the configured allow/review lists")

    def evaluate_all(self,
                     dependencies: Iterable[Dependency]
                     ) -> dict[str, str]:
        return {d.name: self.evaluate(d)[0] for d in dependencies}

    def _matches_deny(self, spdx: str) -> bool:
        for pattern in self.config.deny_patterns:
            if fnmatch.fnmatchcase(spdx, pattern):
                return True
        return False
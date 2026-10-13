"""Phase 10 §68 invariants probe base.

The architecture document records 52 invariants in §68. Each
invariant has at least one named probe method in
:mod:`tests.test_phase_10_invariants`. This module provides the
:class:`InvariantProbe` base class and the :func:`discover_probes`
helper used by the test suite to enumerate probe classes.

The phase ships :data:`INVARIANT_COUNT` = 52; the loader asserts the
discovered count matches this number.
"""

from __future__ import annotations

import abc
import inspect
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Type


INVARIANT_COUNT = 52


@dataclass
class InvariantReport:
    """The result of a single invariant probe execution."""

    invariant_id: str
    label: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "invariantId": self.invariant_id,
            "label": self.label,
            "passed": self.passed,
            "detail": self.detail,
        }


class InvariantProbe(abc.ABC):
    """Abstract §68 invariant probe.

    Each concrete subclass declares a one-attribute class constant
    (:attr:`invariant_id`) and a short label (:attr:`label`). The
    concrete :meth:`probe` method returns the boolean pass verdict
    and a free-form detail string used for failure messages.
    """

    invariant_id: str = ""
    label: str = ""

    @abc.abstractmethod
    def probe(self) -> tuple[bool, str]:
        """Execute the invariant probe and return ``(passed, detail)``."""


def discover_probes(package_globals: Mapping[str, Any]) -> list[Type[InvariantProbe]]:
    """Enumerate every concrete :class:`InvariantProbe` subclass visible
    from ``package_globals``.

    The loader collects every imported class (not just the ones
    referenced by name in the module) so that any
    :class:`InvariantProbe` subclass added by a follow-up change is
    automatically picked up.

    The returned list is sorted by ``invariant_id`` so the produced
    report is deterministic.
    """
    probes: list[Type[InvariantProbe]] = []
    for value in package_globals.values():
        if not inspect.isclass(value):
            continue
        if value is InvariantProbe:
            continue
        if not issubclass(value, InvariantProbe):
            continue
        if inspect.isabstract(value):
            continue
        if not getattr(value, "invariant_id", ""):
            continue
        probes.append(value)
    probes.sort(key=lambda cls: cls.invariant_id)
    return probes

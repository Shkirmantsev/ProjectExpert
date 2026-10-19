"""CLI wrapper for the production-capability gate (PR 12, plan §64).

Runs :func:`pi_platform.core.orchestration.production_capability_gate.run_production_capability_gate`
and prints a structured JSON report to stdout:

.. code-block:: json

    {
      "passed": true,
      "checks": [
        {"name": "inventory:google/embeddinggemma-2", "passed": true, "details": "..."}
      ],
      "summary": "production-capability gate passed: 5 checks"
    }

The exit code is ``0`` when ``passed`` is ``true`` and ``1``
otherwise, so a release pipeline can gate on the process status
alone. Output is pretty-printed with ``indent=2`` by default; the
optional ``--json`` flag switches to single-line machine-readable
JSON.

In-process callers get no flags when they pass nothing (``argv`` of
``None`` means an empty argument list); the module entry point
forwards ``sys.argv[1:]`` explicitly.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from pi_platform.core.orchestration.production_capability_gate import (
    GateReport,
    run_production_capability_gate,
)


__all__ = [
    "cmd_production_capability_gate",
    "report_payload",
]


def report_payload(report: GateReport) -> dict[str, Any]:
    """Render a :class:`GateReport` as the documented CLI payload."""

    checks: list[dict[str, Any]] = [
        {
            "name": verdict.name or verdict.state,
            "passed": verdict.state == "PASS",
            "details": verdict.detail,
        }
        for verdict in report.verdicts
    ]
    failed = [check["name"] for check in checks if not check["passed"]]
    if failed:
        summary = (
            "production-capability gate FAILED: "
            f"{len(failed)} of {len(checks)} checks failed: "
            + ", ".join(failed)
        )
    else:
        summary = f"production-capability gate passed: {len(checks)} checks"
    return {
        "passed": bool(report.passed),
        "checks": checks,
        "summary": summary,
    }


def cmd_production_capability_gate(argv: Sequence[str] | None = None) -> int:
    """Run the gate, print the JSON report, and return the exit code.

    Returns ``0`` when the gate passed and ``1`` otherwise. The
    optional ``--json`` flag prints a single line of machine-readable
    JSON; the default output is pretty-printed with ``indent=2``.
    """

    parser = argparse.ArgumentParser(
        prog="pi_platform.cli.production_capability_gate",
        description=(
            "Run the production-capability release gate and print "
            "a JSON report (exit 0 when the gate passed)."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="emit single-line machine-readable JSON (default: pretty-printed)",
    )
    args = parser.parse_args(list(argv) if argv is not None else [])

    report = run_production_capability_gate()
    payload = report_payload(report)
    if args.json_output:
        print(json.dumps(payload))
    else:
        print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(cmd_production_capability_gate(sys.argv[1:]))
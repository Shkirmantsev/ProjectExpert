"""The ``inference`` command group: plan, doctor and status.

* ``inference plan`` -- read probe evidence, compute the profile, print the
  decision JSON (exactly one JSON object on stdout, nothing else, so the
  deployment launchers can parse it directly).
* ``inference doctor`` -- the full diagnostic report: environment, model
  files with checksums, the evidence, the decision and the rejected
  candidates.
* ``inference status`` -- the status of the configured runtime endpoint.

Evidence input is ``--evidence-b64 <base64 of the evidence JSON>`` (the
form the launchers use, because it survives shell quoting), or
``--evidence <path>``, or ``--evidence -`` for stdin.

Evidence JSON schema (produced by the launchers)::

    {"platform": "linux"|"windows",
     "candidates": [{"backend": "cuda"|"vulkan"|"cpu",
                     "ok": true, "exit_code": 0,
                     "output": "raw probe output"}]}

Decision JSON schema (``plan``)::

    {"ok": true, "backend": "vulkan", "device": "Vulkan0",
     "fit_target_mib": 192, "integrated": false,
     "reason": "...",
     "rejected": [{"backend": "cuda", "reason": "..."}],
     "server_args": ["--embeddings", ...],
     "compose": {"PI_ACCELERATOR": "vulkan", "PI_GPU_DEVICE": "Vulkan0",
                 "PI_FIT_TARGET": "192"}}
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import platform as _platform
import sys
import urllib.error
import urllib.request

from ..adapters.retrieval.gguf_artifacts import (
    GEMMA_FILENAME,
    GEMMA_MODEL_ALIAS,
    GEMMA_PROJECTOR_FILENAME,
    GEMMA_PROJECTOR_SHA256,
    GEMMA_SHA256,
)
from ..core.inference import (
    BackendCandidate,
    build_server_argv,
    compose_device_fragment,
    select_profile,
)

__all__ = [
    "run_inference_command",
    "cmd_plan",
    "cmd_doctor",
    "cmd_status",
    "cmd_benchmark",
    "load_evidence",
    "candidates_from_evidence",
]


#: The fixed corpus the benchmark uses. It is deliberately short and
#: technical so the measurement reflects a realistic retrieval query
#: rather than a single trivial token.
BENCHMARK_TEXTS = (
    "warehouse pallet packing process for the genesys line",
    "TCP retry implementation in the order service",
    "how does the refund approval workflow work",
    "database migration script for the billing schema",
    "kubernetes deployment of the packaging service",
    "HTTP client timeouts and circuit breaker configuration",
)


DEFAULT_CACHE_ROOT = Path("/models")


def _cache_root(args) -> Path:
    cache = getattr(args, "cache", None)
    if cache:
        return Path(cache)
    return Path(os.environ.get("PI_GGUF_CACHE", str(DEFAULT_CACHE_ROOT)))


def load_evidence(args) -> dict:
    """Load the probe evidence JSON from base64, a file or stdin."""

    raw: bytes | None = None
    payload = getattr(args, "evidence_b64", None)
    if payload:
        compact = "".join(payload.split())
        try:
            raw = base64.b64decode(compact, validate=True)
        except Exception as exc:  # noqa: BLE001 - report as a plain error
            raise ValueError(f"--evidence-b64 is not valid base64: {exc}") from exc
    else:
        source = getattr(args, "evidence", None)
        if source is None:
            raise ValueError("provide --evidence-b64 or --evidence (path or '-' for stdin)")
        if source == "-":
            raw = sys.stdin.buffer.read()
        else:
            raw = Path(source).read_bytes()
    try:
        evidence = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"evidence is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be a JSON object")
    return evidence


def candidates_from_evidence(evidence: dict) -> list[BackendCandidate]:
    """Convert the launcher evidence schema into probe candidates."""

    entries = evidence.get("candidates", [])
    if not isinstance(entries, list):
        raise ValueError("evidence 'candidates' must be a list")
    candidates: list[BackendCandidate] = []
    for entry in entries:
        if not isinstance(entry, dict) or "backend" not in entry:
            raise ValueError("each evidence candidate must name a 'backend'")
        candidates.append(
            BackendCandidate(
                backend=str(entry["backend"]),
                ok=bool(entry.get("ok", False)),
                exit_code=int(entry.get("exit_code", -1)),
                output=str(entry.get("output", "")),
                error=entry.get("error"),
            )
        )
    return candidates


def _decision_payload(args, evidence: dict) -> dict:
    candidates = candidates_from_evidence(evidence)
    profile = select_profile(
        candidates, measurements=evidence.get("measurements") or None,
    )
    cache = _cache_root(args)
    # The launcher may run the runtime outside the container filesystem (the
    # native Windows service), so the backbone and projector paths can be
    # given explicitly. They are used verbatim: the planning code never
    # touches the files.
    model_path = getattr(args, "model_path", None) or str(cache / GEMMA_FILENAME)
    projector_path = (
        getattr(args, "projector_path", None)
        or str(cache / GEMMA_PROJECTOR_FILENAME)
    )
    server_args = build_server_argv(
        model_path=model_path,
        projector_path=projector_path,
        alias=GEMMA_MODEL_ALIAS,
        device=profile.device,
        backend=profile.backend,
        fit_target_mib=profile.fit_target_mib,
        host=getattr(args, "host", None) or "127.0.0.1",
        port=int(getattr(args, "port", None) or 8769),
        api_key_file=getattr(args, "api_key_file", None) or str(cache / "llama-api-key"),
    )
    return {
        "ok": True,
        "backend": profile.backend,
        "device": profile.device,
        "fit_target_mib": profile.fit_target_mib,
        "integrated": profile.integrated,
        "reason": profile.reason,
        "rejected": [dict(item) for item in profile.rejected],
        # A single, easily parsed line for the deployment launchers. Parsing
        # the nested array in a shell is fragile; the launcher must not have
        # to understand the JSON shape.
        "rejected_text": "; ".join(
            f"{item['backend']} ({item['reason']})"
            for item in profile.rejected
        ),
        "server_args": server_args,
        "compose": compose_device_fragment(profile),
        "measurements": dict(evidence.get("measurements") or {}),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_files(cache: Path) -> list[dict]:
    files = []
    for name, expected in (
        (GEMMA_FILENAME, GEMMA_SHA256),
        (GEMMA_PROJECTOR_FILENAME, GEMMA_PROJECTOR_SHA256),
    ):
        path = cache / name
        present = path.is_file()
        actual = _sha256(path) if present else None
        files.append(
            {
                "name": name,
                "path": str(path),
                "present": present,
                "sha256": actual,
                "expected_sha256": expected,
                "ok": bool(present and actual == expected),
            }
        )
    return files


def cmd_plan(args) -> int:
    """Compute the inference profile and print the decision JSON."""

    try:
        evidence = load_evidence(args)
        payload = _decision_payload(args, evidence)
    except Exception as exc:  # noqa: BLE001 - always emit one JSON object
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(payload, indent=2))
    return 0


def cmd_doctor(args) -> int:
    """Print the full inference diagnostics as one JSON object."""

    try:
        evidence = load_evidence(args)
        payload = _decision_payload(args, evidence)
    except Exception as exc:  # noqa: BLE001 - always emit one JSON object
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    cache = _cache_root(args)
    payload["platform"] = {
        "system": _platform.system(),
        "release": _platform.release(),
        "machine": _platform.machine(),
        "python": _platform.python_version(),
        "reported": evidence.get("platform"),
        "cache_root": str(cache),
    }
    payload["model_files"] = _model_files(cache)
    payload["evidence"] = evidence
    print(json.dumps(payload, indent=2))
    return 0


def _benchmark_client(args):
    """Return a callable that embeds one text through the runtime."""

    import urllib.error
    import urllib.request

    endpoint = (
        getattr(args, "endpoint", None)
        or os.environ.get("PI_LLAMA_ENDPOINT", "http://127.0.0.1:8769")
    ).rstrip("/")
    key_file = Path(
        os.environ.get("PI_LLAMA_API_KEY_FILE", "/models/llama-api-key")
    )
    token = ""
    if key_file.is_file():
        try:
            token = key_file.read_text().strip().splitlines()
            token = next(
                (line.strip() for line in token
                 if line.strip() and not line.startswith("#")),
                "",
            )
        except OSError:
            token = ""
    headers = {"Content-Type": "application/json"}
    if len(token) >= 32:
        headers["Authorization"] = "Bearer " + token
    timeout = float(getattr(args, "timeout", None) or 120)

    def embed(text: str) -> None:
        request = urllib.request.Request(
            endpoint + "/v1/embeddings",
            data=json.dumps({
                "input": [text], "encoding_format": "float",
            }).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read(1024 * 1024))
        rows = result.get("data", []) if isinstance(result, dict) else []
        vector = rows[0].get("embedding", []) if rows and isinstance(rows[0], dict) else []
        if len(vector) != 768 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vector):
            raise ValueError("benchmark endpoint did not return a valid 768-dimensional embedding")

    return embed, endpoint


def cmd_benchmark(args) -> int:
    """Measure the embedding latency of a running runtime.

    The measurement is what decides whether a GPU profile is worth
    selecting: a GPU that works but is slower than the CPU baseline is
    an optimisation that costs time.
    """

    import statistics
    import time

    iterations = max(1, int(getattr(args, "iterations", None) or 30))
    warmup = max(0, int(getattr(args, "warmup", None) or 5))
    try:
        embed, endpoint = _benchmark_client(args)
    except Exception as exc:  # noqa: BLE001 - always emit one JSON object
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    try:
        for index in range(warmup):
            embed(BENCHMARK_TEXTS[index % len(BENCHMARK_TEXTS)])
        latencies: list[float] = []
        for index in range(iterations):
            started = time.perf_counter()
            embed(BENCHMARK_TEXTS[index % len(BENCHMARK_TEXTS)])
            latencies.append((time.perf_counter() - started) * 1000.0)
    except Exception as exc:  # noqa: BLE001 - always emit one JSON object
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    latencies.sort()
    median = statistics.median(latencies)
    payload = {
        "ok": True,
        "endpoint": endpoint,
        "iterations": iterations,
        "warmup": warmup,
        "median_ms": round(median, 3),
        "mean_ms": round(statistics.mean(latencies), 3),
        "p95_ms": round(latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))], 3),
        "embeddings_per_second": round(1000.0 / median, 3) if median > 0 else 0.0,
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_status(args) -> int:
    """Print the status of the configured runtime endpoint."""

    endpoint = (
        getattr(args, "endpoint", None)
        or os.environ.get("PI_LLAMA_ENDPOINT", "http://127.0.0.1:8769")
    ).rstrip("/")
    key_file = Path(
        os.environ.get("PI_LLAMA_API_KEY_FILE", "/models/llama-api-key")
    )
    payload = {
        "endpoint": endpoint,
        "key_file": str(key_file),
        "key_present": key_file.is_file(),
        "reachable": False,
        "http_status": None,
        "models": [],
    }
    token = None
    if payload["key_present"]:
        try:
            token = key_file.read_text().strip().splitlines()
            token = next((line.strip() for line in token if line.strip() and not line.startswith("#")), "")
        except OSError:
            token = ""
        payload["key_present"] = bool(token and len(token) >= 32)
    headers = {"Accept": "application/json"}
    if token and payload["key_present"]:
        # The bearer token is sent but never printed.
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(endpoint + "/v1/models", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload["http_status"] = getattr(response, "status", 200)
            body = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        payload["error"] = type(exc).__name__
        payload["detail"] = str(exc)[:200]
        print(json.dumps(payload, indent=2))
        return 1
    payload["reachable"] = True
    for entry in body.get("data", []) if isinstance(body, dict) else []:
        if isinstance(entry, dict) and entry.get("id"):
            payload["models"].append(str(entry["id"]))
    print(json.dumps(payload, indent=2))
    return 0


_HANDLERS = {
    "plan": cmd_plan,
    "doctor": cmd_doctor,
    "status": cmd_status,
    "benchmark": cmd_benchmark,
}


def run_inference_command(args) -> int:
    """Dispatch the ``inference`` command group (plan/doctor/status)."""

    subcommand = getattr(args, "inference_command", None)
    handler = _HANDLERS.get(subcommand)
    if handler is None:
        print(json.dumps({
            "error": f"unknown inference subcommand {subcommand!r}",
            "code": "unknown-inference-subcommand",
            "details": {"allowed": sorted(_HANDLERS)},
        }), file=sys.stderr)
        return 2
    return handler(args)
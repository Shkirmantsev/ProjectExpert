"""Select the host route using the production container's network."""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from pi_platform.adapters.retrieval.llama_cpp_embedding_model import _NoRedirect
from pi_platform.core.inference.benchmark import BENCHMARK_TEXTS


_HOSTS = ("host.docker.internal", "host.rancher-desktop.internal")
_PRIVATE_NETWORKS = tuple(
    ipaddress.IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


def _private_address(value: str) -> bool:
    try:
        address = ipaddress.IPv4Address(value)
    except ValueError:
        return False
    return any(address in network for network in _PRIVATE_NETWORKS)


def verify_native_route(*, port: int, model: str, host_ips: list[str], key_file: Path,
                        host_only: bool = False, auth: str = "managed-token") -> dict:
    if not 1 <= port <= 65535 or len(host_ips) > 8 or not all(map(_private_address, host_ips)):
        return {"ok": False, "code": "native_route_invalid"}
    headers = {}
    if auth == "managed-token":
        try:
            token = key_file.read_text().strip()
        except (OSError, UnicodeError):
            return {"ok": False, "code": "native_credentials_unavailable"}
        if len(token) < 32 or not token.isascii() or any(char.isspace() for char in token):
            return {"ok": False, "code": "native_credentials_unavailable"}
        headers["Authorization"] = "Bearer " + token
    elif auth != "none" or not host_only:
        return {"ok": False, "code": "native_route_invalid"}

    # Ignore proxy environment settings and reject redirects before sending a
    # credential. Probe only the engine's reserved host names and host-owned
    # addresses supplied by the launcher. Pin the route to the IP tested here.
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    attempts = []
    seen = set()
    candidates = tuple(host_ips) if host_only else (*_HOSTS, *host_ips)
    for candidate in candidates:
        try:
            addresses = socket.gethostbyname_ex(candidate)[2] if candidate in _HOSTS else [candidate]
        except OSError:
            attempts.append({"route": candidate, "code": "dns_missing"})
            continue
        for address in [item for item in addresses if _private_address(item)][:2]:
            if address in seen:
                continue
            seen.add(address)
            endpoint = f"http://{address}:{port}"
            models_url = endpoint + "/v1/models"
            if headers.get("Authorization"):
                try:
                    with opener.open(models_url, timeout=2):
                        attempts.append({"route": candidate, "code": "native_auth_not_required"})
                        continue
                except HTTPError as exc:
                    code = exc.code
                    exc.close()
                    if code != 401:
                        attempts.append({"route": candidate, "code": f"http_{code}"})
                        continue
                except (OSError, ValueError) as exc:
                    reason = exc.reason if isinstance(exc, URLError) else exc
                    code = "connection_refused" if isinstance(reason, ConnectionRefusedError) else "host_route_unreachable"
                    attempts.append({"route": candidate, "code": code})
                    continue
            try:
                with opener.open(Request(models_url, headers=headers), timeout=3) as response:
                    models = json.loads(response.read(1024 * 1024))
                if not any(item.get("id") == model for item in models["data"]):
                    attempts.append({"route": candidate, "code": "wrong_model"})
                    continue
                from pi_platform.cli.inference import _validate_benchmark_embedding

                request = Request(endpoint + "/v1/embeddings", headers={**headers, "Content-Type": "application/json"}, data=json.dumps({
                    "input": [BENCHMARK_TEXTS[0]], "encoding_format": "float",
                }).encode())
                started = time.perf_counter()
                with opener.open(request, timeout=30) as response:
                    _validate_benchmark_embedding(json.loads(response.read(1024 * 1024)))
                return {"ok": True, "endpoint": endpoint, "route": candidate,
                        "median_ms": round((time.perf_counter() - started) * 1000, 3), "attempts": attempts}
            except HTTPError as exc:
                attempts.append({"route": candidate, "code": f"http_{exc.code}"})
                exc.close()
            except (ValueError, OSError, KeyError, TypeError, AttributeError):
                attempts.append({"route": candidate, "code": "native_smoke_failed"})
    return {"ok": False, "code": "native_route_unverified", "attempts": attempts}

"""Phase 8 §56 URL egress classifier.

Classifies a URL into one of the documented
:class:`EgressChannel` values:

- ``127.0.0.1`` / ``::1`` / ``localhost`` / ``0:0:0:0:0:0:0:1`` ->
  :class:`EgressChannel.LOOPBACK`
- RFC1918 / link-local / RFC4193 addresses ->
  :class:`EgressChannel.LOCAL`
- everything else ->
  :class:`EgressChannel.EXTERNAL`

Malformed URLs fall back to :class:`EgressChannel.UNKNOWN`
and the egress port is expected to treat unknown channels
with the same default-policy rule that it applies to
external destinations.
"""

from __future__ import annotations

import ipaddress
from typing import Optional, Tuple
from urllib.parse import urlparse

from pi_platform.ports.security.egress import EgressChannel


__all__ = [
    "classify_url",
    "is_loopback_host",
    "KNOWN_LOCAL_HOSTS",
]


# Hostnames that always count as loopback for Phase 8.
# The list is intentionally small; Phase 8 trusts only
# these literal labels and the loopback IP ranges from
# :mod:`ipaddress`. Wildcard matches (``*.localhost``)
# are out of scope; the egress port feeds the explicit
# matchers.
KNOWN_LOCAL_HOSTS: Tuple[str, ...] = (
    "localhost",
    "ip6-localhost",
    "ip6-loopback",
)


def is_loopback_host(host: str) -> bool:
    """Return ``True`` when ``host`` matches a documented
    loopback identifier (literal name or IP range).
    """
    if not host:
        return False
    lower = host.lower().strip("[]")
    if lower in KNOWN_LOCAL_HOSTS:
        return True
    try:
        address = ipaddress.ip_address(lower)
    except ValueError:
        return False
    return bool(
        address.is_loopback
        or address.is_private
        and address in ipaddress.ip_network("127.0.0.0/8")
    )


def _classify_address(host: str) -> Optional[EgressChannel]:
    """Return the channel for an IP-bearing host. ``None``
    when the host is not an IP address.
    """
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None
    if address.is_loopback:
        return EgressChannel.LOOPBACK
    if address.is_private:
        return EgressChannel.LOCAL
    if address.is_link_local:
        return EgressChannel.LOCAL
    if address.is_multicast:
        return EgressChannel.LOCAL
    return EgressChannel.EXTERNAL


def classify_url(url: str) -> EgressChannel:
    """Return the resolved :class:`EgressChannel` for
    ``url``.
    """
    if not url:
        return EgressChannel.UNKNOWN
    try:
        parsed = urlparse(url)
    except ValueError:
        return EgressChannel.UNKNOWN
    host = (parsed.hostname or "").lower()
    if not host:
        return EgressChannel.UNKNOWN
    if host in KNOWN_LOCAL_HOSTS:
        return EgressChannel.LOOPBACK
    address_channel = _classify_address(host)
    if address_channel is not None:
        return address_channel
    # A non-IP, non-localhost hostname is treated as
    # external for the Phase 8 default policy. Specific
    # host allow-lists live under the canonical tree per
    # §7.1.
    return EgressChannel.EXTERNAL

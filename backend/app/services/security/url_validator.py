"""URL validation for SSRF protection.

Blocks requests to private/internal IP ranges, cloud metadata services, and
non-HTTP(S) schemes. :func:`validate_url` checks a single URL; :func:`safe_get`
fetches a URL and re-validates **every redirect hop**, closing the
"validate a public URL, then 302 into 169.254.169.254" bypass.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

# CIDR blocks not covered by ipaddress' is_private / is_reserved across the
# Python versions we support.
_EXTRA_BLOCKED = [
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT / carrier-grade NAT (incl. Tailscale)
    ipaddress.ip_network("0.0.0.0/8"),       # "this network"
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("64:ff9b::/96"),    # NAT64 (embeds IPv4 internal targets)
]

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_REDIRECTS = 4


def _is_testing() -> bool:
    """Check if running in test environment."""
    return os.environ.get("FORGE_TESTING", "").lower() in ("1", "true")


class SSRFError(ValueError):
    """Raised when a URL targets a blocked network or scheme."""


def _ip_is_blocked(ip: Any) -> bool:
    """True if ``ip`` (an ipaddress address) is internal/private/reserved.

    IPv4-mapped IPv6 addresses (e.g. ``::ffff:169.254.169.254``) are normalised
    to their IPv4 form before the check so they cannot smuggle past the IPv4
    range tests.
    """
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    return any(ip in network for network in _EXTRA_BLOCKED)


def validate_url(url: str, *, allow_localhost: bool = False) -> str:
    """Validate a URL for SSRF safety.

    Args:
        url: The URL to validate.
        allow_localhost: If True, skip IP range checks (for testing only).

    Returns:
        The validated URL string.

    Raises:
        SSRFError: If the URL targets a blocked resource.
    """
    if not url or not url.strip():
        raise SSRFError("URL is empty")

    parsed = urlparse(url.strip())

    # Check scheme
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SSRFError(
            f"URL scheme '{parsed.scheme}' is not allowed. Only HTTP and HTTPS are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL has no hostname")

    if allow_localhost or _is_testing():
        return url

    # Resolve hostname to IP(s) and check every result against blocked ranges.
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFError(f"Cannot resolve hostname '{hostname}'") from exc

    if not results:
        raise SSRFError(f"Cannot resolve hostname '{hostname}'")

    for *_unused, sockaddr in results:
        ip = ipaddress.ip_address(sockaddr[0])
        if _ip_is_blocked(ip):
            raise SSRFError(
                "URL resolves to a blocked IP range. "
                "Access to internal/private networks is not allowed."
            )

    return url


async def safe_get(
    url: str,
    *,
    timeout: float = 30.0,
    max_redirects: int = _MAX_REDIRECTS,
    allow_localhost: bool = False,
    client: httpx.AsyncClient | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """GET ``url`` with SSRF protection that re-validates every redirect hop.

    The HTTP client is configured with ``follow_redirects=False`` so each
    ``Location`` is run through :func:`validate_url` before it is followed.
    This prevents a validated public URL from redirecting into an internal
    target. Pass ``client`` to inject a transport (used in tests).
    """
    validate_url(url, allow_localhost=allow_localhost)

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)
    try:
        current = url
        for _ in range(max_redirects + 1):
            resp = await client.get(current, **kwargs)
            if resp.is_redirect and "location" in resp.headers:
                next_url = str(httpx.URL(current).join(resp.headers["location"]))
                validate_url(next_url, allow_localhost=allow_localhost)
                current = next_url
                continue
            return resp
    finally:
        if owns_client:
            await client.aclose()

    raise SSRFError(f"Too many redirects (more than {max_redirects})")

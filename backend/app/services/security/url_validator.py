"""URL validation for SSRF protection.

Blocks requests to private/internal IP ranges, cloud metadata services,
and non-HTTP(S) schemes.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

# Private/internal IP ranges that should never be accessed via user-supplied URLs
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("10.0.0.0/8"),          # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),       # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),      # Private Class C
    ipaddress.ip_network("169.254.0.0/16"),      # Link-local / cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),           # Current network
    ipaddress.ip_network("::1/128"),             # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),            # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),           # IPv6 link-local
]

_ALLOWED_SCHEMES = {"http", "https"}

def _is_testing() -> bool:
    """Check if running in test environment."""
    return os.environ.get("FORGE_TESTING", "").lower() in ("1", "true")


class SSRFError(ValueError):
    """Raised when a URL targets a blocked network or scheme."""


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

    # Resolve hostname to IP and check against blocked ranges
    try:
        # getaddrinfo handles both IPv4 and IPv6
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _family, _type, _proto, _canonname, sockaddr in results:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            for network in _BLOCKED_NETWORKS:
                if ip in network:
                    raise SSRFError(
                        f"URL resolves to blocked IP range ({network}). "
                        "Access to internal/private networks is not allowed."
                    )
    except socket.gaierror as exc:
        raise SSRFError(f"Cannot resolve hostname '{hostname}'") from exc

    return url

"""Regression tests for the SSRF hardening (redirect re-validation + IP gaps).

These cover the bypasses the original happy-path tests missed:
- redirect following into an internal target,
- IPv4-mapped IPv6 addresses,
- CGNAT / carrier-grade-NAT range.
"""

from __future__ import annotations

import ipaddress

import httpx
import pytest

from app.services.security import url_validator as uv

# ── IP classification gaps ────────────────────────────────────────────────


def test_ipv4_mapped_ipv6_metadata_blocked():
    """::ffff:169.254.169.254 must normalise to its v4 form and be blocked."""
    assert uv._ip_is_blocked(ipaddress.ip_address("::ffff:169.254.169.254")) is True


def test_ipv4_mapped_ipv6_public_allowed():
    """A public address wrapped as IPv4-mapped IPv6 stays allowed."""
    assert uv._ip_is_blocked(ipaddress.ip_address("::ffff:8.8.8.8")) is False


def test_cgnat_range_blocked():
    """100.64.0.0/10 (CGNAT, incl. Tailscale) is internal."""
    assert uv._ip_is_blocked(ipaddress.ip_address("100.64.1.1")) is True


def test_loopback_and_private_blocked():
    for addr in ("127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.169.254", "::1"):
        assert uv._ip_is_blocked(ipaddress.ip_address(addr)) is True


def test_public_ip_allowed():
    assert uv._ip_is_blocked(ipaddress.ip_address("93.184.216.34")) is False


# ── redirect re-validation ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_safe_get_blocks_redirect_to_internal(monkeypatch):
    """A 302 into the cloud-metadata IP must raise, not be followed."""
    seen: list[str] = []

    def fake_validate(url: str, **_kwargs) -> str:
        seen.append(url)
        if "169.254" in url:
            raise uv.SSRFError("URL resolves to a blocked IP range")
        return url

    monkeypatch.setattr(uv, "validate_url", fake_validate)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    with pytest.raises(uv.SSRFError, match="blocked IP range"):
        await uv.safe_get("http://public.example.test/", client=client)
    await client.aclose()

    # The redirect target was validated (and rejected) — not silently followed.
    assert any("169.254" in u for u in seen)


@pytest.mark.asyncio
async def test_safe_get_returns_non_redirect_response(monkeypatch):
    """A normal 200 passes through unchanged."""
    monkeypatch.setattr(uv, "validate_url", lambda url, **_k: url)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="hello")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    resp = await uv.safe_get("http://public.example.test/", client=client)
    await client.aclose()
    assert resp.status_code == 200
    assert resp.text == "hello"


@pytest.mark.asyncio
async def test_safe_get_follows_safe_redirect(monkeypatch):
    """A redirect to another public URL is followed and re-validated."""
    monkeypatch.setattr(uv, "validate_url", lambda url, **_k: url)
    hops: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "http://public.example.test/final"})
        return httpx.Response(200, text="final")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    resp = await uv.safe_get("http://public.example.test/start", client=client)
    await client.aclose()
    assert resp.text == "final"
    assert len(hops) == 2


# ── code-executor sandbox bypasses ────────────────────────────────────────


def test_code_executor_blocks_open_alias():
    """Aliasing the open builtin must be rejected (the classic denylist bypass)."""
    from app.services.tools.code_executor import code_executor

    result = code_executor.invoke("r = open\nprint(r('/etc/passwd').read())")
    assert "Blocked" in result


def test_code_executor_blocks_os_exec():
    """os.execv / os.popen escapes must be rejected."""
    from app.services.tools.code_executor import code_executor

    assert "Blocked" in code_executor.invoke("import os\nos.execv('/bin/sh', ['sh'])")
    assert "Blocked" in code_executor.invoke("p = os.popen\nprint(p('id').read())")


def test_code_executor_blocks_dunder_introspection():
    """The ().__class__.__bases__ subclasses escape must be rejected."""
    from app.services.tools.code_executor import code_executor

    result = code_executor.invoke("print(().__class__.__bases__[0].__subclasses__())")
    assert "Blocked" in result


def test_code_executor_runs_safe_imports():
    """Allowlisted stdlib (math) still works."""
    from app.services.tools.code_executor import code_executor

    result = code_executor.invoke("import math\nprint(math.factorial(5))")
    assert "120" in result

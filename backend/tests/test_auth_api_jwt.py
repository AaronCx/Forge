"""Regression test for QA Finding #5 — local-mode JWTs lacked exp claims."""

from __future__ import annotations

from datetime import UTC, datetime


def test_jwt_payload_has_iat_and_exp():
    """`_build_jwt_payload` must include both iat and exp."""
    from app.routers.auth_api import _build_jwt_payload

    payload = _build_jwt_payload("user-123", "user@example.com")

    assert "iat" in payload, "JWT must include iat"
    assert "exp" in payload, "JWT must include exp"
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"

    # Sanity: exp is in the future, lifetime is between 1h and 30d.
    now = int(datetime.now(UTC).timestamp())
    assert payload["exp"] > now
    assert 3600 <= (payload["exp"] - payload["iat"]) <= 60 * 60 * 24 * 30

"""Regression test for QA Finding #5 — local-mode JWTs lacked exp claims."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


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


@pytest.mark.asyncio
async def test_api_key_auth_resolves_user():
    """An `af_` Bearer key authenticates to its owning user (QA Finding #6)."""
    from app.routers.auth import get_current_user

    with patch("app.db._db") as mock_db:
        row = MagicMock()
        row.data = {"id": "k1", "user_id": "u-42"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = row
        user = await get_current_user(authorization="Bearer af_sometoken")
    assert user.id == "u-42"


@pytest.mark.asyncio
async def test_api_key_auth_rejects_unknown_key():
    from app.routers.auth import get_current_user

    with patch("app.db._db") as mock_db:
        row = MagicMock()
        row.data = None
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = row
        with pytest.raises(HTTPException) as exc:
            await get_current_user(authorization="Bearer af_bad")
    assert exc.value.status_code == 401

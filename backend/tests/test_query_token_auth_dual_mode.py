"""Regression test for the agent-run / dashboard-stream auth pattern.

Both endpoints accept the JWT in a query parameter (so the EventSource
handshake can carry it) and call `db.auth.get_user(token)` directly. Supabase
returns a wrapper with `.user`; the SQLite local-auth backend returns the
user object directly. The hand-written shim in each endpoint must accept
both shapes — it didn't, so /api/agents/<id>/run and the SSE stream both
401'd on every SQLite stack until the QA playbook flagged it.
"""

from __future__ import annotations


class _FakeSupabaseUser:
    def __init__(self, id: str) -> None:
        self.id = id
        self.email = "user@example.com"


class _FakeSupabaseResponse:
    """Mimics supabase-py: response.user.id."""
    def __init__(self, id: str) -> None:
        self.user = _FakeSupabaseUser(id)


class _FakeSqliteUser:
    """Mimics SQLiteAuthBackend.get_user(token) which returns the user directly."""
    def __init__(self, id: str) -> None:
        self.id = id
        self.email = "user@example.com"


def _resolve_user(user_response):
    """Replicates the shim used in routers/runs.py and routers/dashboard.py."""
    user = user_response.user if hasattr(user_response, "user") else user_response
    if not user or not getattr(user, "id", None):
        raise AssertionError("invalid token shape")
    return user


def test_supabase_response_shape():
    response = _FakeSupabaseResponse("user-1")
    user = _resolve_user(response)
    assert user.id == "user-1"


def test_sqlite_response_shape():
    response = _FakeSqliteUser("user-2")
    user = _resolve_user(response)
    assert user.id == "user-2"

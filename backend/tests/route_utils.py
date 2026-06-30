"""Helpers for enumerating an app's routes across FastAPI versions.

FastAPI 0.138 changed ``include_router`` to register lazy ``_IncludedRouter``
wrapper objects on ``app.routes`` instead of eagerly flattening every included
route into the top-level list. Those wrappers do not expose ``.path``; the real
sub-routes live under ``original_router.routes`` with the include ``prefix``
applied separately. These helpers walk that structure so tests can keep
asserting on the full set of registered paths regardless of FastAPI version.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


def iter_app_routes(app: Any) -> Iterator[tuple[str, Any]]:
    """Yield ``(full_path, route)`` for every leaf route registered on ``app``.

    Traverses FastAPI 0.138+ ``_IncludedRouter`` wrappers recursively, prepending
    each include prefix so the yielded path matches the externally served URL.
    """

    def _walk(routes: list[Any], prefix: str) -> Iterator[tuple[str, Any]]:
        for route in routes:
            original = getattr(route, "original_router", None)
            if original is not None:
                sub_prefix = (
                    getattr(getattr(route, "include_context", None), "prefix", "")
                    or ""
                )
                yield from _walk(original.routes, prefix + sub_prefix)
            elif hasattr(route, "path"):
                yield prefix + route.path, route

    yield from _walk(app.routes, "")


def app_route_paths(app: Any) -> list[str]:
    """Return the full path of every leaf route registered on ``app``."""
    return [path for path, _ in iter_app_routes(app)]

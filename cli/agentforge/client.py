"""HTTP client for AgentForge API."""

import httpx
from agentforge.config import get_api_url, get_api_key


def _headers() -> dict[str, str]:
    key = get_api_key()
    if key:
        return {"Authorization": f"Bearer {key}"}
    return {}


def get(path: str, params: dict | None = None) -> dict | list:
    """Make a GET request to the API."""
    url = f"{get_api_url()}{path}"
    r = httpx.get(url, headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def post(path: str, json: dict | None = None) -> dict:
    """Make a POST request to the API."""
    url = f"{get_api_url()}{path}"
    r = httpx.post(url, headers=_headers(), json=json, timeout=60)
    r.raise_for_status()
    return r.json()


def put(path: str, json: dict | None = None) -> dict:
    """Make a PUT request to the API."""
    url = f"{get_api_url()}{path}"
    r = httpx.put(url, headers=_headers(), json=json, timeout=60)
    r.raise_for_status()
    return r.json()


def delete(path: str) -> None:
    """Make a DELETE request to the API."""
    url = f"{get_api_url()}{path}"
    r = httpx.delete(url, headers=_headers(), timeout=30)
    r.raise_for_status()


def stream_sse(path: str, params: dict | None = None):
    """Stream SSE events from the API. Yields parsed data strings."""
    url = f"{get_api_url()}{path}"
    with httpx.stream("GET", url, headers=_headers(), params=params, timeout=None) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                yield line[6:]


def stream_sse_post(path: str, json: dict | None = None):
    """Stream SSE events from a POST endpoint. Yields parsed data strings."""
    url = f"{get_api_url()}{path}"
    with httpx.stream("POST", url, headers={**_headers(), "Content-Type": "application/json"}, json=json, timeout=None) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                yield line[6:]

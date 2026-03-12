import os

import httpx
from langchain.tools import tool


@tool
async def web_search(query: str) -> str:
    """Search the web for information on a given query. Returns top search results with titles, links, and snippets."""
    api_key = os.getenv("SERPAPI_KEY", "")

    if not api_key:
        return "Web search is not configured. Please set SERPAPI_KEY."

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "api_key": api_key,
                "engine": "google",
                "num": 5,
            },
            timeout=15.0,
        )

    if response.status_code != 200:
        return f"Search failed with status {response.status_code}"

    data = response.json()
    results = data.get("organic_results", [])

    if not results:
        return "No results found."

    output = []
    for r in results[:5]:
        title = r.get("title", "")
        link = r.get("link", "")
        snippet = r.get("snippet", "")
        output.append(f"**{title}**\n{link}\n{snippet}")

    return "\n\n".join(output)

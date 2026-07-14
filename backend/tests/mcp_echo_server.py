"""A minimal reference MCP server over stdio, for client_v2 tests.

Run as ``python tests/mcp_echo_server.py``; exposes one ``echo`` tool.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("echo")


@mcp.tool()
def echo(text: str) -> str:
    """Echo the input text back to the caller."""
    return f"echo: {text}"


if __name__ == "__main__":
    mcp.run()  # stdio transport by default

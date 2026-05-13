"""mcp-chainladder — MCP server exposing actuarial chain-ladder reserving
tools to Claude (and any other MCP-aware client).

Pure-numeric math lives in `chainladder.py`; the MCP plumbing lives in
`server.py`. The default entry point is `mcp_chainladder.__main__:main`,
which runs the server over stdio.
"""
from mcp_chainladder.server import mcp

__all__ = ["mcp"]
__version__ = "1.2.2"

"""Command-line entry point — runs the MCP server over stdio.

Wire-up for Claude Desktop / Cursor / Cline:

    {
      "mcpServers": {
        "chainladder": {
          "command": "uvx",
          "args": ["mcp-chainladder"]
        }
      }
    }

Running via `python -m mcp_chainladder` works too.
"""
from mcp_chainladder.server import mcp


def main() -> None:
    """Run the MCP server. Blocks on stdio until the client disconnects."""
    mcp.run()


if __name__ == "__main__":
    main()

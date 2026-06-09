from __future__ import annotations

from .mcp_remote import create_stdio_server

mcp = create_stdio_server()


if __name__ == "__main__":
    mcp.run()

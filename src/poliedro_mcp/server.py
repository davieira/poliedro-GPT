from __future__ import annotations

from .mcp_tools import create_local_server

mcp = create_local_server()


if __name__ == "__main__":
    mcp.run()

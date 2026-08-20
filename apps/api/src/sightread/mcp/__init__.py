"""MCP server package — a thin shell over the service layer (docs/mcp.md)."""

from .server import mcp_session_manager, mount_mcp

__all__ = ["mcp_session_manager", "mount_mcp"]

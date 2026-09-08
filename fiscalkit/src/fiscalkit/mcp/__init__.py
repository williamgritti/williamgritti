"""MCP server exposing fiscalkit's tools to AI agents."""

from .server import TOOL_FUNCTIONS, build_server, main

__all__ = ["TOOL_FUNCTIONS", "build_server", "main"]

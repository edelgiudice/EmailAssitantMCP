"""Email assistant MCP server package."""

from .cli import main
from .server import build_server

__all__ = ["build_server", "main"]

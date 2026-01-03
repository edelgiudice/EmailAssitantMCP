"""Command-line interface for running the Email Assistant MCP server."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .server import build_server


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments used to run the MCP server."""
    parser = argparse.ArgumentParser(
        description="Run the Email Assistant MCP server over stdio or SSE"
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse"),
        default="stdio",
        help="Select 'stdio' for MCP over stdio or 'sse' for the SSE transport",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind when using the SSE transport (ignored for stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind when using the SSE transport (ignored for stdio)",
    )
    parser.add_argument(
        "--sse-path",
        default="/sse",
        help="HTTP path for SSE events (ignored for stdio)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point configured in pyproject.toml."""
    args = parse_args(argv)
    server = build_server()

    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(
            transport="sse",
            host=args.host,
            port=args.port,
            path=args.sse_path,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

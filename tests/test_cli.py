"""Unit tests for the CLI entrypoint."""

from __future__ import annotations

import unittest
from unittest import mock

from email_assistant_mcp.cli import main, parse_args


class ParseArgsTests(unittest.TestCase):
    def test_transport_defaults_to_stdio(self) -> None:
        args = parse_args([])
        self.assertEqual(args.transport, "stdio")

    def test_host_defaults_to_loopback(self) -> None:
        args = parse_args([])
        self.assertEqual(args.host, "127.0.0.1")

    def test_port_defaults_to_8000(self) -> None:
        args = parse_args([])
        self.assertEqual(args.port, 8000)

    def test_sse_path_defaults_to_events_endpoint(self) -> None:
        args = parse_args([])
        self.assertEqual(args.sse_path, "/sse")

    def test_transport_accepts_sse(self) -> None:
        args = parse_args(["--transport", "sse"])
        self.assertEqual(args.transport, "sse")

    def test_host_accepts_custom_value(self) -> None:
        args = parse_args(["--host", "0.0.0.0"])
        self.assertEqual(args.host, "0.0.0.0")

    def test_port_accepts_custom_value(self) -> None:
        args = parse_args(["--port", "9001"])
        self.assertEqual(args.port, 9001)

    def test_sse_path_accepts_custom_value(self) -> None:
        args = parse_args(["--sse-path", "/events"])
        self.assertEqual(args.sse_path, "/events")


class MainTests(unittest.TestCase):
    @mock.patch("email_assistant_mcp.cli.build_server")
    def test_stdio_transport_invokes_server(self, mock_build_server: mock.MagicMock) -> None:
        server = mock_build_server.return_value
        main(["--transport", "stdio"])
        server.run.assert_called_once_with(transport="stdio")

    @mock.patch("email_assistant_mcp.cli.build_server")
    def test_sse_transport_invokes_server_with_custom_options(
        self, mock_build_server: mock.MagicMock
    ) -> None:
        server = mock_build_server.return_value

        main(
            [
                "--transport",
                "sse",
                "--host",
                "localhost",
                "--port",
                "9000",
                "--sse-path",
                "/stream",
            ]
        )

        server.run.assert_called_once_with(
            transport="sse", host="localhost", port=9000, path="/stream"
        )

    @mock.patch("email_assistant_mcp.cli.build_server")
    def test_main_returns_success_exit_code(self, mock_build_server: mock.MagicMock) -> None:
        mock_build_server.return_value.run.return_value = None
        exit_code = main([])
        self.assertEqual(exit_code, 0)

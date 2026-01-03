"""Unit tests for the FastMCP server factory."""

from __future__ import annotations

import unittest
from unittest import mock

from email_assistant_mcp import server


class BuildServerTests(unittest.TestCase):
    def test_build_server_registers_tools_with_default_store(self) -> None:
        mock_fastmcp = mock.sentinel.fastmcp_instance
        mock_store = mock.sentinel.credential_store
        with mock.patch.object(server, "FastMCP", return_value=mock_fastmcp) as fastmcp_ctor, mock.patch.object(
            server.CredentialStore,
            "default",
            return_value=mock_store,
        ) as default_store, mock.patch.object(server, "register_all_tools") as register_all_tools:
            result = server.build_server()

        self.assertIs(result, mock_fastmcp)
        fastmcp_ctor.assert_called_once_with(
            name=server.SERVER_NAME,
            instructions=server.SERVER_INSTRUCTIONS,
        )
        default_store.assert_called_once_with()
        register_all_tools.assert_called_once_with(mock_fastmcp, mock_store)


if __name__ == "__main__":
    unittest.main()

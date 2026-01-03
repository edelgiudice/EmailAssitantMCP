"""Tests for the bootstrap tool registrations."""

from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest import mock

from email_assistant_mcp.credential_store import CredentialStore
from email_assistant_mcp.tools import bootstrap
from tests.helpers import ToolCapturingFastMCP


class BootstrapToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ToolCapturingFastMCP()
        self.credential_store = mock.create_autospec(CredentialStore, instance=True)
        bootstrap.register_bootstrap_tools(self.server, self.credential_store)

    def run_tool(self, tool_name: str, *args: Any, **kwargs: Any) -> Any:
        tool = self.server.tools[tool_name]
        return asyncio.run(tool(*args, **kwargs))

    def test_health_check_reports_ready(self) -> None:
        result = self.run_tool("health_check")
        self.assertEqual(result, "email assistant server ready")

    def test_list_email_accounts_returns_descriptions(self) -> None:
        self.credential_store.list_config_ids.return_value = ["personal", "work"]
        descriptions = {
            "personal": {
                "config_id": "personal",
                "provider": "gmail",
                "email_address": "personal@example.com",
                "display_name": "Personal",
            },
            "work": {
                "config_id": "work",
                "provider": "gmail",
                "email_address": "work@example.com",
                "display_name": "Work",
            },
        }
        self.credential_store.describe_config.side_effect = lambda cid: descriptions[cid].copy()

        result = self.run_tool("list_email_accounts")

        self.credential_store.list_config_ids.assert_called_once_with()
        self.assertEqual(result, [descriptions["personal"], descriptions["work"]])

    def test_current_email_account_without_activation_is_inactive(self) -> None:
        result = self.run_tool("current_email_account")

        self.assertEqual(result, {"status": "inactive"})
        self.credential_store.describe_config.assert_not_called()

    def test_activate_email_account_sets_current_metadata(self) -> None:
        metadata = {
            "config_id": "primary",
            "provider": "gmail",
            "email_address": "***@example.com",  # Redacted by describe_config()
            "display_name": "User",
        }
        self.credential_store.describe_config.return_value = metadata.copy()

        activation_message = self.run_tool("activate_email_account", "primary")
        current = self.run_tool("current_email_account")

        self.assertEqual(activation_message, "Activated gmail account for ***@example.com")
        self.assertEqual(current, {**metadata, "status": "active"})
        self.assertEqual(
            self.credential_store.describe_config.call_args_list,
            [mock.call("primary"), mock.call("primary")],
        )

    def test_setup_gmail_account_stores_config(self) -> None:
        with mock.patch.object(
            bootstrap,
            "complete_gmail_setup",
            return_value=mock.sentinel.gmail_config,
        ) as complete_gmail:
            message = self.run_tool(
                "setup_gmail_account",
                "primary",
                "user@example.com",
                "client-id",
                "client-secret",
                display_name="Alias",
                open_browser=False,
            )

        complete_gmail.assert_called_once_with(
            email_address="user@example.com",
            display_name="Alias",
            client_id="client-id",
            client_secret="client-secret",
            open_browser=False,
        )
        self.credential_store.save_config.assert_called_once_with("primary", mock.sentinel.gmail_config)
        self.assertEqual(message, "Stored Gmail config 'primary' for user@example.com.")


if __name__ == "__main__":
    unittest.main()

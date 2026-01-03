"""Tests for the combined Manage tool."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from email_assistant_mcp.credential_store import CredentialStore
from email_assistant_mcp.tools import manage, messages, rules
from tests.helpers import ToolCapturingFastMCP


class ManageToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ToolCapturingFastMCP()
        self.credential_store = mock.create_autospec(CredentialStore, instance=True)
        self.client = mock.Mock()
        self.client.supports_folder_creation = True
        self.message_tools = messages.MessageTools(provider_clients={"gmail": self.client})
        messages.register_message_tools(
            self.server, # type: ignore[arg-type]
            self.credential_store,
            message_tools=self.message_tools,
        )
        self.tmp_rules = tempfile.TemporaryDirectory()
        self.rule_store = rules.RuleStore(rules_dir=Path(self.tmp_rules.name))
        self.manage_tools = manage.ManageTools(
            message_tools=self.message_tools,
            rule_store=self.rule_store,
        )
        manage.register_manage_tools(
            self.server, # type: ignore[arg-type]
            self.credential_store,
            manage_tools=self.manage_tools,
        )
        self.config = mock.Mock(provider="gmail", email_address="user@example.com")
        self.credential_store.get_config.return_value = self.config

        self.rule_store.save_rule(
            rules.RuleRecord(
                id=1,
                name="Daily triage",
                summary="Route daily updates.",
                ref_command="move_emails",
                version=1,
                prompt="If the message is an automated daily update, move it.",
                expiration_date=None,
                auto_execute=False,
            )
        )

    def tearDown(self) -> None:
        self.tmp_rules.cleanup()

    def run_tool(self, name: str, *args: Any, **kwargs: Any) -> Any:
        tool = self.server.tools[name]
        return asyncio.run(tool(*args, **kwargs))

    def test_manage_defaults_dates_and_returns_rules(self) -> None:
        self.client.search_messages.return_value = {
            "messages": [{"id": "m1", "subject": "Daily update"}],
            "total_count": 1,
            "truncated": False,
        }
        self.manage_tools._today_iso_date = lambda: "2024-03-05"  # type: ignore[assignment]

        result = self.run_tool("manage", "primary")

        self.assertEqual(result["from_date"], "2024-03-05")
        self.assertEqual(result["to_date"], "2024-03-05")
        self.assertIn("config_id", result)
        self.assertIn("provider", result)
        self.assertEqual(result["messages"][0]["id"], "m1")
        self.assertEqual(result["active_rule_count"], 1)
        self.assertEqual(len(result["rules"]), 1)

        self.assertEqual(result["rules"][0]["name"], "Daily triage")


if __name__ == "__main__":
    unittest.main()

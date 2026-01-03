"""Tests for the message-focused email tools."""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any
from unittest import mock

from email_assistant_mcp.credential_store import CredentialStore
from email_assistant_mcp.tools import messages
from tests.helpers import ToolCapturingFastMCP


class MessageToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ToolCapturingFastMCP()
        self.credential_store = mock.create_autospec(CredentialStore, instance=True)
        self.client = mock.Mock()
        self.client.supports_folder_creation = True
        self.tools = messages.MessageTools(provider_clients={"gmail": self.client})
        messages.register_message_tools(
            self.server,
            self.credential_store,
            message_tools=self.tools,
        )
        self.config = mock.Mock(provider="gmail", email_address="user@example.com")
        self.credential_store.get_config.return_value = self.config

    def run_tool(self, name: str, *args: Any, **kwargs: Any) -> Any:
        tool = self.server.tools[name]
        return asyncio.run(tool(*args, **kwargs))

    def read_resource(self, uri: str) -> dict[str, Any]:
        resource = self.server.resources[uri]
        return json.loads(asyncio.run(resource.read()))

    def test_draft_email_registers_preview_resource(self) -> None:
        self.client.create_draft.return_value = {
            "draft_id": "r1",
            "message_id": "m1",
            "thread_id": "t1",
        }

        result = self.run_tool(
            "draft_email",
            "primary",
            to=["user@example.com"],
            subject="Hello",
            body_text="Body text",
        )

        self.client.create_draft.assert_called_once()
        self.assertEqual(result["draft_id"], "r1")
        preview_payload = self.read_resource(result["preview_resource"])
        self.assertEqual(preview_payload["subject"], "Hello")
        self.assertEqual(preview_payload["body_preview"], "Body text")

    def test_get_emails_returns_all_messages(self) -> None:
        """Test that get_emails returns all messages in single response."""
        self.client.search_messages.return_value = {
            "messages": [
                {"id": "m1", "subject": "Hi"},
                {"id": "m2", "subject": "Hello"},
            ],
            "total_count": 2,
            "truncated": False,
        }

        result = self.run_tool(
            "get_emails",
            "primary",
            date_from="2024-01-02",
            date_to="2024-01-05",
        )

        # Verify response structure
        self.assertEqual(result["config_id"], "primary")
        self.assertEqual(result["provider"], "gmail")
        self.assertEqual(len(result["messages"]), 2)
        self.assertEqual(result["total_count"], 2)
        self.assertFalse(result["truncated"])
        self.assertIn("filters_applied", result)

        # Verify normalized dates
        filters_applied = result["filters_applied"]
        self.assertTrue(filters_applied["date_from"].endswith("00:00:00+00:00"))
        self.assertTrue(filters_applied["date_to"].endswith("23:59:59+00:00"))

    def test_get_emails_requires_date_range_when_no_filters(self) -> None:
        with self.assertRaisesRegex(ValueError, "date_from and date_to"):
            self.run_tool("get_emails", "primary")

    def test_fetch_email_full_registers_resource(self) -> None:
        self.client.fetch_message_full.return_value = {
            "attachments": [],
            "id": "m1",
        }

        result = self.run_tool("fetch_email_full", "primary", "m1")

        self.client.fetch_message_full.assert_called_once_with(self.config, "m1")
        full_payload = self.read_resource(result["resource_uri"])
        self.assertEqual(full_payload["message_id"], "m1")

    def test_batch_move_emails_resolves_destinations(self) -> None:
        """Test that batch_move_emails resolves folder names for each message."""
        self.client.list_folders.return_value = [
            {"id": "Label_1", "name": "Archive", "type": "user"},
            {"id": "Label_2", "name": "Work", "type": "user"},
        ]
        self.client.batch_move_messages.return_value = {
            "success_count": 2,
            "failure_count": 0,
            "success": [
                {"message_id": "m1", "final_labels": ["Label_1"]},
                {"message_id": "m2", "final_labels": ["Label_2"]},
            ],
            "failures": [],
        }

        result = self.run_tool(
            "batch_move_emails",
            "primary",
            message_operations=[
                {"message_id": "m1", "destination_folder": "archive"},
                {"message_id": "m2", "destination_folder": "work"},
            ],
        )

        self.client.batch_move_messages.assert_called_once()
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["failure_count"], 0)

    def test_batch_move_emails_handles_location_labels(self) -> None:
        """Test that batch_move_emails properly manages Gmail location labels."""
        self.config.provider = "gmail"
        self.client.list_folders.return_value = [
            {"id": "Label_1", "name": "Archive", "type": "user"},
        ]
        self.client.batch_move_messages.return_value = {
            "success_count": 1,
            "failure_count": 0,
            "success": [{"message_id": "m1", "final_labels": ["Label_1"]}],
            "failures": [],
        }

        result = self.run_tool(
            "batch_move_emails",
            "primary",
            message_operations=[
                {"message_id": "m1", "destination_folder": "Archive"},
            ],
        )

        # Verify batch_move_messages was called with proper label management
        call_args = self.client.batch_move_messages.call_args
        operations = call_args[0][1]  # Second positional arg
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]["add_labels"], ["Label_1"])
        # Should remove INBOX and other location labels
        self.assertIn("INBOX", operations[0]["remove_labels"])

    def test_mark_for_deletion_creates_folder_when_missing(self) -> None:
        """Test that mark_for_deletion creates the folder if it doesn't exist."""
        self.client.list_folders.return_value = []
        self.client.create_folder.return_value = {"id": "Label_mfd", "name": "mark_for_deletion"}
        self.client.batch_move_messages.return_value = {
            "success_count": 2,
            "failure_count": 0,
            "success": [
                {"message_id": "a", "final_labels": ["Label_mfd"]},
                {"message_id": "b", "final_labels": ["Label_mfd"]},
            ],
            "failures": [],
        }

        result = self.run_tool(
            "mark_for_deletion",
            "primary",
            message_ids=["a", "b"],
        )

        self.client.create_folder.assert_called_once()
        self.assertEqual(result["success_count"], 2)


if __name__ == "__main__":
    unittest.main()

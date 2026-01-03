"""Tests for the folder-related email tools."""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any
from unittest import mock

from email_assistant_mcp.credential_store import CredentialStore
from email_assistant_mcp.tools import folder
from tests.helpers import ToolCapturingFastMCP


class FolderToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ToolCapturingFastMCP()
        self.credential_store = mock.create_autospec(CredentialStore, instance=True)
        gmail_client = mock.Mock()
        gmail_client.supports_folder_creation = True
        self.folder_tools = folder.FolderTools(
            provider_clients={"gmail": gmail_client},
        )
        self.gmail_client = gmail_client
        self.gmail_folders = self.folder_tools._folders_for_provider("gmail")
        gmail_client.list_folders.return_value = self.gmail_folders
        folder.register_folder_tools(
            self.server,
            self.credential_store,
            folder_tools=self.folder_tools,
        )

    def run_tool(self, tool_name: str, *args: Any, **kwargs: Any) -> Any:
        tool = self.server.tools[tool_name]
        return asyncio.run(tool(*args, **kwargs))

    def test_list_email_folders_registers_resource(self) -> None:
        config = mock.Mock(provider="gmail", email_address="user@example.com")
        self.credential_store.get_config.return_value = config
        result = self.run_tool("list_email_folders", "primary")

        resource_uri = "resource://email-folders/user%40example.com"
        self.assertEqual(
            result,
            {
                "resource_uri": resource_uri,
                "email_address": "user@example.com",
                "provider": "gmail",
                "folder_count": len(self.gmail_folders),
            },
        )
        resource = self.server.resources[resource_uri]
        payload = json.loads(asyncio.run(resource.read()))
        self.assertEqual(payload["email_address"], "user@example.com")
        self.assertEqual(payload["provider"], "gmail")
        self.assertEqual(len(payload["folders"]), len(self.gmail_folders))

    def test_list_email_folders_requires_email_address(self) -> None:
        config = mock.Mock(provider="gmail", email_address=None)
        self.credential_store.get_config.return_value = config

        with self.assertRaisesRegex(ValueError, "missing the email address"):
            self.run_tool("list_email_folders", "missing")

    def test_create_email_folder_calls_creator(self) -> None:
        config = mock.Mock(provider="gmail", email_address="user@example.com")
        self.credential_store.get_config.return_value = config
        self.gmail_client.create_folder.return_value = {
            "id": "Label_1",
            "name": "Projects",
            "type": "user",
        }

        result = self.run_tool(
            "create_email_folder",
            "primary",
            "Projects",
            parent_folder="Work",
        )

        self.gmail_client.create_folder.assert_called_once_with(
            config,
            "Projects",
            "Work",
        )
        self.assertEqual(
            result,
            {
                "config_id": "primary",
                "email_address": "user@example.com",
                "provider": "gmail",
                "folder": {"id": "Label_1", "name": "Projects", "type": "user"},
                "resource_uri": "resource://email-folders/user%40example.com",
                "folder_count": len(self.gmail_folders),
            },
        )
        resource = self.server.resources["resource://email-folders/user%40example.com"]
        payload = json.loads(asyncio.run(resource.read()))
        self.assertEqual(len(payload["folders"]), len(self.gmail_folders))

    def test_create_email_folder_refreshes_existing_resource(self) -> None:
        config = mock.Mock(provider="gmail", email_address="user@example.com")
        self.credential_store.get_config.return_value = config
        updated_folders = [*self.gmail_folders, {"id": "Label_2", "name": "Finance", "type": "user"}]
        self.gmail_client.list_folders.side_effect = [
            self.gmail_folders,
            updated_folders,
        ]
        self.gmail_client.create_folder.return_value = {
            "id": "Label_2",
            "name": "Finance",
            "type": "user",
        }
        resource_uri = "resource://email-folders/user%40example.com"

        self.run_tool("list_email_folders", "primary")
        initial_payload = json.loads(
            asyncio.run(self.server.resources[resource_uri].read())
        )
        self.assertEqual(len(initial_payload["folders"]), len(self.gmail_folders))

        result = self.run_tool("create_email_folder", "primary", "Finance")

        self.assertEqual(result["resource_uri"], resource_uri)
        self.assertEqual(result["folder_count"], len(updated_folders))
        refreshed_payload = json.loads(
            asyncio.run(self.server.resources[resource_uri].read())
        )
        self.assertEqual(len(refreshed_payload["folders"]), len(updated_folders))
        self.assertEqual(refreshed_payload["folders"][-1]["name"], "Finance")

    def test_create_email_folder_requires_name(self) -> None:
        config = mock.Mock(provider="gmail", email_address="user@example.com")
        self.credential_store.get_config.return_value = config

        with self.assertRaisesRegex(ValueError, "folder name is required"):
            self.run_tool("create_email_folder", "primary", "   ")

    def test_create_email_folder_requires_supported_provider(self) -> None:
        config = mock.Mock(provider="unknown", email_address="user@example.com")
        self.credential_store.get_config.return_value = config

        with self.assertRaisesRegex(ValueError, "Folder creation is not supported"):
            self.run_tool("create_email_folder", "primary", "Projects")


if __name__ == "__main__":
    unittest.main()

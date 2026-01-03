"""Unit tests for the JSON-backed credential store."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Any
from unittest import mock

from email_assistant_mcp.config import GmailOAuthConfig
from email_assistant_mcp.credential_store import (
    CredentialNotFoundError,
    CredentialStore,
    DEFAULT_STORE_PATH,
)


class CredentialStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.store_path = Path(self.tmp_dir.name) / "configs.json"
        self.store = CredentialStore(self.store_path)

    def make_gmail_config(self, **overrides: Any) -> GmailOAuthConfig:
        """Return a Gmail configuration populated with predictable defaults."""
        data: dict[str, Any] = {
            "email_address": "user@example.com",
            "display_name": "User",
            "refresh_token": "test-fake-refresh-token-not-real-12345",
            "client_id": "test-fake-client-id-not-real-abcde",
            "client_secret": "test-fake-client-secret-not-real-67890",
            "token_uri": "https://oauth.example/token",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
        }
        data.update(overrides)
        return GmailOAuthConfig(**data)

    def write_payloads(self, payloads: dict[str, Any]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(json.dumps(payloads), encoding="utf-8")

    def test_list_config_ids_returns_sorted_identifiers(self) -> None:
        self.write_payloads({"work": {}, "personal": {}, "alerts": {}})

        result = self.store.list_config_ids()

        self.assertEqual(result, ["alerts", "personal", "work"])

    def test_list_config_ids_raises_error_for_corrupted_file(self) -> None:
        self.write_payloads({})
        self.store_path.write_text("[]", encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            self.store.list_config_ids()

        # Verify error message uses only filename, not full path
        error_msg = str(ctx.exception)
        self.assertIn(self.store_path.name, error_msg)
        self.assertNotIn(str(self.store_path.parent), error_msg)
        self.assertEqual(error_msg, f"Credential store file '{self.store_path.name}' is corrupted")

    def test_get_config_returns_dataclass_payload(self) -> None:
        payload = self.make_gmail_config(display_name=None)
        self.write_payloads({"work": asdict(payload)})

        config = self.store.get_config("work")

        self.assertIsInstance(config, GmailOAuthConfig)
        self.assertEqual(config.email_address, "user@example.com")
        self.assertIsNone(config.display_name)

    def test_get_config_payload_missing_raises_error(self) -> None:
        with self.assertRaises(CredentialNotFoundError):
            self.store.get_config_payload("missing")

    def test_save_config_persists_serialized_config(self) -> None:
        config = self.make_gmail_config()

        self.store.save_config("demo", config)

        payloads = json.loads(self.store_path.read_text(encoding="utf-8"))
        self.assertEqual(payloads["demo"]["email_address"], "user@example.com")
        self.assertEqual(payloads["demo"]["provider"], "gmail")

    def test_save_config_creates_parent_directory(self) -> None:
        custom_path = Path(self.tmp_dir.name) / "nested" / "store" / "configs.json"
        store = CredentialStore(custom_path)

        store.save_config("demo", self.make_gmail_config())

        self.assertTrue(custom_path.exists())

    def test_delete_config_removes_entry(self) -> None:
        self.write_payloads({"obsolete": {}, "active": {}})

        self.store.delete_config("obsolete")

        payloads = json.loads(self.store_path.read_text(encoding="utf-8"))
        self.assertNotIn("obsolete", payloads)
        self.assertIn("active", payloads)

    def test_delete_config_missing_raises_error(self) -> None:
        with self.assertRaises(CredentialNotFoundError):
            self.store.delete_config("missing")

    def test_describe_config_returns_redacted_metadata(self) -> None:
        config = self.make_gmail_config(display_name="Alias")
        self.write_payloads({"work": asdict(config)})

        result = self.store.describe_config("work")

        self.assertEqual(
            result,
            {
                "config_id": "work",
                "provider": "gmail",
                "email_address": "***@example.com",  # Redacted for security
                "display_name": "Alias",
            },
        )


class DefaultStoreTests(unittest.TestCase):
    def test_default_uses_environment_override(self) -> None:
        custom_path = Path("D:/tmp/custom.json")
        with mock.patch.dict(os.environ, {"EMAIL_ASSISTANT_CONFIG_STORE": str(custom_path)}):
            store = CredentialStore.default()

        self.assertEqual(store.path, custom_path)

    def test_default_without_env_returns_standard_path(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            store = CredentialStore.default()

        self.assertEqual(store.path, DEFAULT_STORE_PATH)


if __name__ == "__main__":
    unittest.main()

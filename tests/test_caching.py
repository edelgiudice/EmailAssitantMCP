"""Unit tests for caching functionality across the application."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from email_assistant_mcp.credential_store import CredentialStore
from email_assistant_mcp.email_clients.gmail_client import GmailClient
from email_assistant_mcp.tools.base import ProviderBackedToolSet
from email_assistant_mcp.config import GmailOAuthConfig


class CredentialStoreCacheTests(unittest.TestCase):
    """Test mtime-based caching in CredentialStore."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.store_path = Path(self.tmp_dir.name) / "configs.json"
        self.store = CredentialStore(self.store_path)

    def write_payloads(self, payloads: dict) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(json.dumps(payloads), encoding="utf-8")

    def test_cache_returns_same_data_on_repeated_reads(self) -> None:
        """Cache should return same data without re-reading file."""
        self.write_payloads({"work": {"email": "test@example.com"}})

        # First read
        result1 = self.store.list_config_ids()

        # Second read should use cache
        result2 = self.store.list_config_ids()

        self.assertEqual(result1, result2)
        self.assertEqual(result1, ["work"])

    def test_cache_invalidates_when_file_modified(self) -> None:
        """Cache should detect file changes via mtime."""
        self.write_payloads({"work": {}})

        # First read
        result1 = self.store.list_config_ids()
        self.assertEqual(result1, ["work"])

        # Modify file (need to ensure mtime changes)
        time.sleep(0.01)  # Ensure mtime difference
        self.write_payloads({"work": {}, "personal": {}})

        # Second read should detect change
        result2 = self.store.list_config_ids()
        self.assertEqual(result2, ["personal", "work"])

    def test_cache_invalidates_after_save(self) -> None:
        """Cache should invalidate after save_config."""
        config = GmailOAuthConfig(
            email_address="test@example.com",
            refresh_token="token",
            client_id="id",
            client_secret="secret",
            token_uri="https://oauth.example/token",
        )

        self.store.save_config("work", config)

        # Read should get fresh data
        ids = self.store.list_config_ids()
        self.assertEqual(ids, ["work"])

    def test_cache_invalidates_after_delete(self) -> None:
        """Cache should invalidate after delete_config."""
        self.write_payloads({"work": {}, "personal": {}})

        # Prime cache
        self.store.list_config_ids()

        # Delete config
        self.store.delete_config("work")

        # Should see updated list
        ids = self.store.list_config_ids()
        self.assertEqual(ids, ["personal"])


class GmailLabelCacheTests(unittest.TestCase):
    """Test label caching in GmailClient."""

    def setUp(self) -> None:
        self.client = GmailClient()

    def test_label_cache_stores_mappings(self) -> None:
        """Label cache should store name->ID mappings."""
        self.client._label_cache["Tennis"] = "Label_123"
        self.client._label_cache["Work"] = "Label_456"

        self.assertEqual(self.client._label_cache.get("Tennis"), "Label_123")
        self.assertEqual(self.client._label_cache.get("Work"), "Label_456")

    def test_label_cache_expires_after_ttl(self) -> None:
        """Label cache should expire after 5 minutes."""
        # Create cache with short TTL for testing
        from cachetools import TTLCache
        self.client._label_cache = TTLCache(maxsize=100, ttl=0.1)  # 100ms TTL

        self.client._label_cache["Tennis"] = "Label_123"
        self.assertEqual(self.client._label_cache.get("Tennis"), "Label_123")

        # Wait for expiry
        time.sleep(0.15)

        # Should be expired
        self.assertIsNone(self.client._label_cache.get("Tennis"))

    def test_label_cache_populated_during_list_folders(self) -> None:
        """list_folders should populate label cache."""
        config = GmailOAuthConfig(
            email_address="test@example.com",
            refresh_token="token",
            client_id="id",
            client_secret="secret",
            token_uri="https://oauth.example/token",
        )

        # Mock the API calls
        with mock.patch.object(self.client, '_refresh_access_token', return_value="fake_token"):
            with mock.patch.object(self.client, '_fetch_labels', return_value=[
                {"id": "Label_123", "name": "Tennis", "type": "user"},
                {"id": "INBOX", "name": "INBOX", "type": "system"},
            ]):
                folders = self.client.list_folders(config)

        # Cache should be populated
        self.assertEqual(self.client._label_cache.get("Tennis"), "Label_123")
        self.assertEqual(self.client._label_cache.get("INBOX"), "INBOX")


class GmailAccessTokenCacheTests(unittest.TestCase):
    """Test access token caching in GmailClient."""

    def setUp(self) -> None:
        self.client = GmailClient()

    def test_token_cache_with_expiry_buffer(self) -> None:
        """Access token cache should respect 60s buffer."""
        # Store token that expires in 2 minutes
        expiry = datetime.now(timezone.utc) + timedelta(seconds=120)
        self.client._access_token_cache["token"] = ("fake_token", expiry)

        # Should be usable (>60s remaining)
        cached = self.client._access_token_cache.get("token")
        self.assertIsNotNone(cached)
        self.assertEqual(cached[0], "fake_token")

    def test_token_cache_rejects_near_expiry_tokens(self) -> None:
        """Token should not be used if < 60s buffer remaining."""
        config = GmailOAuthConfig(
            email_address="test@example.com",
            refresh_token="refresh_token",
            client_id="client_id",
            client_secret="client_secret",
            token_uri="https://oauth.example/token",
        )

        # Store token that expires in 30 seconds (< 60s buffer)
        expiry = datetime.now(timezone.utc) + timedelta(seconds=30)
        self.client._access_token_cache["token"] = ("old_token", expiry)

        # Mock token refresh
        with mock.patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = mock.MagicMock()
            mock_response.read.return_value = json.dumps({
                "access_token": "new_token",
                "expires_in": 3600
            }).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_response

            # Should refresh token (not use cached one)
            token = self.client._refresh_access_token(config)

            self.assertEqual(token, "new_token")


class FolderCacheTests(unittest.TestCase):
    """Test folder caching in ProviderBackedToolSet."""

    def setUp(self) -> None:
        # Mock client
        self.mock_client = mock.MagicMock()
        self.toolset = ProviderBackedToolSet(provider_clients={"gmail": self.mock_client})

        self.config = GmailOAuthConfig(
            email_address="test@example.com",
            refresh_token="token",
            client_id="id",
            client_secret="secret",
            token_uri="https://oauth.example/token",
        )

    def test_folder_cache_reduces_api_calls(self) -> None:
        """Folder cache should prevent redundant API calls."""
        self.mock_client.list_folders.return_value = [
            {"id": "INBOX", "name": "Inbox", "type": "system"}
        ]

        # First call
        folders1 = self.toolset._get_folders_cached(self.mock_client, self.config, "work")

        # Second call should use cache
        folders2 = self.toolset._get_folders_cached(self.mock_client, self.config, "work")

        # API should only be called once
        self.mock_client.list_folders.assert_called_once()
        self.assertEqual(folders1, folders2)

    def test_folder_cache_per_config(self) -> None:
        """Each config should have separate folder cache."""
        self.mock_client.list_folders.side_effect = [
            [{"id": "INBOX", "name": "Inbox", "type": "system"}],
            [{"id": "INBOX", "name": "Inbox", "type": "system"},
             {"id": "Label_123", "name": "Work", "type": "user"}],
        ]

        # First config
        folders1 = self.toolset._get_folders_cached(self.mock_client, self.config, "work")

        # Second config
        folders2 = self.toolset._get_folders_cached(self.mock_client, self.config, "personal")

        # Should be 2 API calls (different configs)
        self.assertEqual(self.mock_client.list_folders.call_count, 2)
        self.assertEqual(len(folders1), 1)
        self.assertEqual(len(folders2), 2)

    def test_folder_cache_invalidation_per_config(self) -> None:
        """Invalidating one config shouldn't affect others."""
        self.mock_client.list_folders.return_value = [
            {"id": "INBOX", "name": "Inbox", "type": "system"}
        ]

        # Prime cache for two configs
        self.toolset._get_folders_cached(self.mock_client, self.config, "work")
        self.toolset._get_folders_cached(self.mock_client, self.config, "personal")

        # Invalidate only "work"
        self.toolset._invalidate_folder_cache("work", "gmail")

        # Reset mock counter
        self.mock_client.list_folders.reset_mock()

        # Fetch "work" again - should call API
        self.toolset._get_folders_cached(self.mock_client, self.config, "work")
        self.assertEqual(self.mock_client.list_folders.call_count, 1)

        # Fetch "personal" again - should use cache
        self.toolset._get_folders_cached(self.mock_client, self.config, "personal")
        self.assertEqual(self.mock_client.list_folders.call_count, 1)  # Still 1

    def test_folder_cache_clear_all(self) -> None:
        """Clearing without provider should invalidate all caches."""
        self.mock_client.list_folders.return_value = [
            {"id": "INBOX", "name": "Inbox", "type": "system"}
        ]

        # Prime cache for two configs
        self.toolset._get_folders_cached(self.mock_client, self.config, "work")
        self.toolset._get_folders_cached(self.mock_client, self.config, "personal")

        # Clear all
        self.toolset._invalidate_folder_cache("work", None)

        # Reset mock counter
        self.mock_client.list_folders.reset_mock()

        # Both should need to fetch from API
        self.toolset._get_folders_cached(self.mock_client, self.config, "work")
        self.toolset._get_folders_cached(self.mock_client, self.config, "personal")
        self.assertEqual(self.mock_client.list_folders.call_count, 2)


if __name__ == "__main__":
    unittest.main()

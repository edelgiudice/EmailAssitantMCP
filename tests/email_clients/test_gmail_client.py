"""Unit tests for the Gmail client helper."""

from __future__ import annotations

import base64
import io
import unittest
from types import SimpleNamespace
from unittest import mock
from urllib import error

from email_assistant_mcp.config import GmailOAuthConfig
from email_assistant_mcp.email_clients.gmail_client import GmailClient


def _sample_message_payload() -> dict[str, object]:
    plain = base64.urlsafe_b64encode(b"Plain body").decode("utf-8")
    html = base64.urlsafe_b64encode(b"<p>HTML body</p>").decode("utf-8")
    return {
        "id": "m1",
        "threadId": "t1",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "snippet text",
        "internalDate": "1700000000000",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Hello"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "dest@example.com"},
                {"name": "Date", "value": "Fri, 01 Dec 2023 12:00:00 +0000"},
            ],
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": plain}},
                {"mimeType": "text/html", "body": {"data": html}},
                {
                    "mimeType": "application/pdf",
                    "filename": "file.pdf",
                    "body": {"attachmentId": "att1", "size": 42},
                },
            ],
        },
    }


class GmailClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = GmailClient()
        self.config = GmailOAuthConfig(email_address="user@example.com")

    def test_create_draft_posts_encoded_message(self) -> None:
        payload = {
            "to": ["dest@example.com"],
            "subject": "Status",
            "body_text": "Hello",
            "thread_id": "thread",
        }
        with mock.patch.object(self.client, "_refresh_access_token", return_value="token") as refresh, mock.patch.object(
            self.client,
            "_gmail_request",
            return_value={"id": "draft_1", "message": {"id": "m1", "threadId": "thread"}},
        ) as request_call:
            result = self.client.create_draft(self.config, payload)

        refresh.assert_called_once_with(self.config)
        request_call.assert_called_once()
        args, kwargs = request_call.call_args
        self.assertTrue(kwargs["payload"]["message"]["raw"])
        self.assertEqual(result["draft_id"], "draft_1")

    def test_search_messages_builds_query_and_fetches_details(self) -> None:
        list_response = {
            "messages": [{"id": "m1"}],
            "resultSizeEstimate": 1,
        }
        message_payload = _sample_message_payload()
        request_calls: list[tuple] = []

        def fake_request(token: str, method: str, url: str, **kwargs):
            request_calls.append((method, url, kwargs))
            if url.endswith("/messages"):
                return list_response
            return message_payload

        with mock.patch.object(self.client, "_refresh_access_token", return_value="token") as refresh, mock.patch.object(
            self.client,
            "_gmail_request",
            side_effect=fake_request,
        ) as request_call:
            result = self.client.search_messages(
                self.config,
                {
                    "subject": "Reports",
                    "recipient": "dest@example.com",
                    "date_from": "2024-01-01T00:00:00+00:00",
                    "date_to": "2024-01-02T23:59:59+00:00",
                },
            )

        refresh.assert_called_once()
        self.assertEqual(result["total_count"], 1)
        self.assertIn("truncated", result)
        self.assertEqual(len(result["messages"]), 1)
        first_call = request_calls[0]
        self.assertIn("subject:", first_call[2]["params"]["q"])
        # Detail call requests the full format
        self.assertEqual(request_calls[1][2]["params"], {"format": "full"})
        message = result["messages"][0]
        self.assertEqual(message["id"], "m1")
        self.assertTrue(message["has_attachments"])

    def test_fetch_message_full_returns_envelope(self) -> None:
        payload = _sample_message_payload()
        with mock.patch.object(self.client, "_refresh_access_token", return_value="token"), mock.patch.object(
            self.client,
            "_gmail_request",
            return_value=payload,
        ):
            result = self.client.fetch_message_full(self.config, "m1")

        self.assertEqual(result["id"], "m1")
        self.assertIn("text_body", result)
        self.assertTrue(result["attachments"])

    def test_batch_move_messages_single_destination(self) -> None:
        """Test batch move with multiple messages to same destination."""
        batch_response = (
            b'--batch_response\r\n'
            b'Content-Type: application/http\r\n'
            b'\r\n'
            b'HTTP/1.1 200 OK\r\n'
            b'Content-Type: application/json\r\n'
            b'\r\n'
            b'{"id": "m1", "threadId": "t1", "labelIds": ["Label_1"]}\r\n'
            b'--batch_response\r\n'
            b'Content-Type: application/http\r\n'
            b'\r\n'
            b'HTTP/1.1 200 OK\r\n'
            b'Content-Type: application/json\r\n'
            b'\r\n'
            b'{"id": "m2", "threadId": "t2", "labelIds": ["Label_1"]}\r\n'
            b'--batch_response--'
        )

        mock_response = mock.MagicMock()
        mock_response.read.return_value = batch_response
        mock_response.headers.get.return_value = 'multipart/mixed; boundary=batch_response'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with mock.patch.object(self.client, "_refresh_access_token", return_value="token"), \
             mock.patch.object(self.client, "_fetch_labels", return_value=[
                 {"id": "Label_1", "name": "Work"}
             ]), \
             mock.patch("email_assistant_mcp.email_clients.gmail_client.request.urlopen", return_value=mock_response):
            result = self.client.batch_move_messages(
                self.config,
                [
                    {"message_id": "m1", "add_labels": ["Label_1"], "remove_labels": ["INBOX"]},
                    {"message_id": "m2", "add_labels": ["Label_1"], "remove_labels": ["INBOX"]},
                ],
            )

        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["failure_count"], 0)
        self.assertEqual(len(result["success"]), 2)

    def test_batch_move_messages_different_destinations(self) -> None:
        """Test batch move with messages going to different destinations."""
        batch_response = (
            b'--batch_response\r\n'
            b'Content-Type: application/http\r\n'
            b'\r\n'
            b'HTTP/1.1 200 OK\r\n'
            b'Content-Type: application/json\r\n'
            b'\r\n'
            b'{"id": "m1", "threadId": "t1", "labelIds": ["Label_1"]}\r\n'
            b'--batch_response\r\n'
            b'Content-Type: application/http\r\n'
            b'\r\n'
            b'HTTP/1.1 200 OK\r\n'
            b'Content-Type: application/json\r\n'
            b'\r\n'
            b'{"id": "m2", "threadId": "t2", "labelIds": ["Label_2"]}\r\n'
            b'--batch_response--'
        )

        mock_response = mock.MagicMock()
        mock_response.read.return_value = batch_response
        mock_response.headers.get.return_value = 'multipart/mixed; boundary=batch_response'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with mock.patch.object(self.client, "_refresh_access_token", return_value="token"), \
             mock.patch.object(self.client, "_fetch_labels", return_value=[
                 {"id": "Label_1", "name": "Work"},
                 {"id": "Label_2", "name": "Personal"}
             ]), \
             mock.patch("email_assistant_mcp.email_clients.gmail_client.request.urlopen", return_value=mock_response):
            result = self.client.batch_move_messages(
                self.config,
                [
                    {"message_id": "m1", "add_labels": ["Label_1"], "remove_labels": ["INBOX"]},
                    {"message_id": "m2", "add_labels": ["Label_2"], "remove_labels": ["INBOX"]},
                ],
            )

        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["failure_count"], 0)

    def test_batch_move_handles_partial_failures(self) -> None:
        """Test batch move with some messages failing."""
        batch_response = (
            b'--batch_response\r\n'
            b'Content-Type: application/http\r\n'
            b'\r\n'
            b'HTTP/1.1 200 OK\r\n'
            b'Content-Type: application/json\r\n'
            b'\r\n'
            b'{"id": "m1", "threadId": "t1", "labelIds": ["Label_1"]}\r\n'
            b'--batch_response\r\n'
            b'Content-Type: application/http\r\n'
            b'\r\n'
            b'HTTP/1.1 404 NOT FOUND\r\n'
            b'Content-Type: application/json\r\n'
            b'\r\n'
            b'{"error": {"code": 404, "message": "Message not found", "status": "NOT_FOUND"}}\r\n'
            b'--batch_response--'
        )

        mock_response = mock.MagicMock()
        mock_response.read.return_value = batch_response
        mock_response.headers.get.return_value = 'multipart/mixed; boundary=batch_response'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with mock.patch.object(self.client, "_refresh_access_token", return_value="token"), \
             mock.patch.object(self.client, "_fetch_labels", return_value=[
                 {"id": "Label_1", "name": "Work"}
             ]), \
             mock.patch("email_assistant_mcp.email_clients.gmail_client.request.urlopen", return_value=mock_response):
            result = self.client.batch_move_messages(
                self.config,
                [
                    {"message_id": "m1", "add_labels": ["Label_1"], "remove_labels": ["INBOX"]},
                    {"message_id": "m2", "add_labels": ["Label_1"], "remove_labels": ["INBOX"]},
                ],
            )

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["failures"][0]["message_id"], "m2")
        self.assertEqual(result["failures"][0]["error_code"], 404)

    def test_label_cache_reduces_api_calls(self) -> None:
        """Test that label cache reduces redundant API calls."""
        from datetime import datetime, timezone

        self.client._label_cache = {"Work": "Label_1", "Personal": "Label_2"}
        self.client._label_cache_time = datetime.now(timezone.utc)

        with mock.patch.object(self.client, "_refresh_access_token", return_value="token"), \
             mock.patch.object(self.client, "_fetch_labels") as fetch_labels:
            labels = self.client._resolve_label_names("token", ["Work", "Personal", "INBOX"])

        # Should not call _fetch_labels since cache is fresh
        fetch_labels.assert_not_called()
        self.assertEqual(labels, ["Label_1", "Label_2", "INBOX"])

    def test_label_cache_refreshes_when_stale(self) -> None:
        """Test that label cache refreshes on cache miss."""
        # Clear the cache to simulate it being empty/expired
        self.client._label_cache.clear()

        with mock.patch.object(self.client, "_refresh_access_token", return_value="token"), \
             mock.patch.object(self.client, "_fetch_labels", return_value=[
                 {"id": "Label_1", "name": "Work"},
                 {"id": "Label_2", "name": "Personal"}
             ]) as fetch_labels:
            labels = self.client._resolve_label_names("token", ["Work"])

        # Should call _fetch_labels since cache is empty (cache miss)
        fetch_labels.assert_called_once()
        self.assertEqual(labels, ["Label_1"])

    def test_resolve_label_names_passes_through_label_ids(self) -> None:
        """Test that label IDs (Label_*) are passed through unchanged."""
        from datetime import datetime, timezone

        self.client._label_cache = {"Work": "Label_1"}
        self.client._label_cache_time = datetime.now(timezone.utc)

        with mock.patch.object(self.client, "_refresh_access_token", return_value="token"), \
             mock.patch.object(self.client, "_fetch_labels") as fetch_labels:
            # Mix of label ID, system label, and name
            labels = self.client._resolve_label_names("token", ["Label_23", "INBOX", "Work"])

        # Should not call _fetch_labels since Label_23 passes through
        fetch_labels.assert_not_called()
        self.assertEqual(labels, ["Label_23", "INBOX", "Label_1"])

    def test_batch_move_splits_over_100_messages(self) -> None:
        """Test that batch operations automatically split for >100 messages."""
        # Create 150 message operations
        operations = [
            {"message_id": f"m{i}", "add_labels": ["Label_1"], "remove_labels": ["INBOX"]}
            for i in range(150)
        ]

        batch_response = (
            b'--batch_response\r\n'
            b'Content-Type: application/http\r\n'
            b'\r\n'
            b'HTTP/1.1 200 OK\r\n'
            b'Content-Type: application/json\r\n'
            b'\r\n'
            b'{"id": "m0", "threadId": "t0", "labelIds": ["Label_1"]}\r\n'
            b'--batch_response--'
        )

        mock_response = mock.MagicMock()
        mock_response.read.return_value = batch_response
        mock_response.headers.get.return_value = 'multipart/mixed; boundary=batch_response'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with mock.patch.object(self.client, "_refresh_access_token", return_value="token"), \
             mock.patch.object(self.client, "_fetch_labels", return_value=[
                 {"id": "Label_1", "name": "Work"}
             ]), \
             mock.patch("email_assistant_mcp.email_clients.gmail_client.request.urlopen", return_value=mock_response) as urlopen:
            result = self.client.batch_move_messages(self.config, operations)

        # Should make 2 batch calls: 100 + 50
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(result["total_count"], 150)

    def test_create_folder_combines_parent_and_returns_folder(self) -> None:
        client = GmailClient()
        config = GmailOAuthConfig(email_address="user@example.com")
        label_payload = {"id": "Label_2", "name": "Projects/2024", "type": "user"}
        with mock.patch.object(client, "_refresh_access_token", return_value="token") as refresh_token, mock.patch.object(
            client,
            "_create_label",
            return_value=label_payload,
        ) as create_label:
            folder = client.create_folder(config, "2024", parent_folder="Projects")

        refresh_token.assert_called_once_with(config)
        create_label.assert_called_once_with("token", "Projects/2024")
        self.assertEqual(
            folder,
            {"id": "Label_2", "name": "Projects/2024", "type": "user"},
        )


class GmailTokenTests(unittest.TestCase):
    @mock.patch("email_assistant_mcp.email_clients.gmail_client.request.urlopen")
    def test_refresh_access_token_returns_token(self, mock_urlopen: mock.Mock) -> None:
        response = mock.MagicMock()
        response.read.return_value = b'{"access_token": "abc123"}'
        response.__enter__.return_value = response
        mock_urlopen.return_value = response
        config = SimpleNamespace(
            client_id="id",
            client_secret="test-fake-client-secret-not-real-67890",
            refresh_token="test-fake-refresh-token-not-real-12345",
            token_uri="https://example.com/token",
        )

        token = GmailClient()._refresh_access_token(config)  # type: ignore[arg-type]

        self.assertEqual(token, "abc123")

    @mock.patch("email_assistant_mcp.email_clients.gmail_client.request.urlopen")
    def test_refresh_access_token_requires_access_token(self, mock_urlopen: mock.Mock) -> None:
        response = mock.MagicMock()
        response.read.return_value = b"{}"
        response.__enter__.return_value = response
        mock_urlopen.return_value = response
        config = SimpleNamespace(
            client_id="id",
            client_secret="test-fake-client-secret-not-real-67890",
            refresh_token="test-fake-refresh-token-not-real-12345",
            token_uri="https://example.com/token",
        )

        with self.assertRaises(RuntimeError):
            GmailClient()._refresh_access_token(config)  # type: ignore[arg-type]

    @mock.patch("email_assistant_mcp.email_clients.gmail_client.request.urlopen")
    def test_refresh_access_token_does_not_log_token_at_info_level(self, mock_urlopen: mock.Mock) -> None:
        """Test that access token is NOT logged at INFO level."""
        response = mock.MagicMock()
        response.read.return_value = b'{"access_token": "test-secret-token-abcdefghijklmnop", "expires_in": 3599}'
        response.__enter__.return_value = response
        mock_urlopen.return_value = response
        config = SimpleNamespace(
            client_id="id",
            client_secret="test-fake-client-secret-not-real-67890",
            refresh_token="test-fake-refresh-token-not-real-12345",
            token_uri="https://example.com/token",
        )

        with self.assertLogs("email_assistant_mcp.email_clients.gmail_client", level="INFO") as log_capture:
            token = GmailClient()._refresh_access_token(config)  # type: ignore[arg-type]

        self.assertEqual(token, "test-secret-token-abcdefghijklmnop")

        # Verify token does NOT appear in INFO level logs
        info_logs = [record.message for record in log_capture.records if record.levelname == "INFO"]
        for log_message in info_logs:
            self.assertNotIn("test-secret-token-abcdefghijklmnop", log_message,
                           "Access token should not appear in INFO level logs")

    @mock.patch("email_assistant_mcp.email_clients.gmail_client.request.urlopen")
    def test_refresh_access_token_logs_redacted_token_at_debug_level(self, mock_urlopen: mock.Mock) -> None:
        """Test that access token IS logged (redacted) at DEBUG level."""
        response = mock.MagicMock()
        response.read.return_value = b'{"access_token": "test-secret-token-abcdefghijklmnop", "expires_in": 3599}'
        response.__enter__.return_value = response
        mock_urlopen.return_value = response
        config = SimpleNamespace(
            client_id="id",
            client_secret="test-fake-client-secret-not-real-67890",
            refresh_token="test-fake-refresh-token-not-real-12345",
            token_uri="https://example.com/token",
        )

        with self.assertLogs("email_assistant_mcp.email_clients.gmail_client", level="DEBUG") as log_capture:
            token = GmailClient()._refresh_access_token(config)  # type: ignore[arg-type]

        self.assertEqual(token, "test-secret-token-abcdefghijklmnop")

        # Verify token appears in DEBUG logs (redacted)
        debug_logs = [record.message for record in log_capture.records if record.levelname == "DEBUG"]
        token_logged = False
        for log_message in debug_logs:
            if "Access token details" in log_message or "token=" in log_message:
                token_logged = True
                # Verify the full token does NOT appear (should be redacted)
                self.assertNotIn("test-secret-token-abcdefghijklmnop", log_message,
                               "Full access token should not appear even at DEBUG level")
                # Verify redacted format appears (first 4 chars...last 4 chars)
                self.assertIn("test...mnop", log_message,
                            "Redacted token should appear at DEBUG level")
                break

        self.assertTrue(token_logged, "Token should be logged at DEBUG level")


class GmailErrorHandlingTests(unittest.TestCase):
    """Test error handling and logging for network failures."""

    def setUp(self) -> None:
        self.client = GmailClient()
        self.config = GmailOAuthConfig(email_address="user@example.com")

    @mock.patch("email_assistant_mcp.email_clients.gmail_client.request.urlopen")
    def test_fetch_labels_logs_http_error_with_redacted_emails(self, mock_urlopen: mock.Mock) -> None:
        """Verify HTTP errors are logged with email redaction and duration tracking."""
        # Create HTTPError with error detail containing email addresses
        error_detail = b'{"error": {"message": "Invalid credentials for user@example.com"}}'
        http_error = error.HTTPError(
            "url", 403, "Forbidden", {}, io.BytesIO(error_detail)
        )
        mock_urlopen.side_effect = http_error

        with self.assertLogs("email_assistant_mcp.email_clients.gmail_client", level="ERROR") as logs:
            with self.assertRaises(error.HTTPError):
                self.client._fetch_labels("fake_token")

        # Verify error was logged
        self.assertEqual(len(logs.output), 1)
        log_message = logs.output[0]

        # Verify log contains expected fields
        self.assertIn("status=403", log_message)
        self.assertIn("duration_ms=", log_message)
        self.assertIn("Gmail label fetch failed", log_message)

        # Verify email address was redacted (should be ***@example.com, not user@example.com)
        self.assertIn("***@example.com", log_message)
        self.assertNotIn("user@example.com", log_message)

    @mock.patch("email_assistant_mcp.email_clients.gmail_client.request.urlopen")
    def test_gmail_request_logs_url_error_with_duration(self, mock_urlopen: mock.Mock) -> None:
        """Verify URLError network failures are logged with duration tracking."""
        # Create URLError (e.g., DNS failure, connection refused)
        url_error = error.URLError("Connection refused")
        mock_urlopen.side_effect = url_error

        with self.assertLogs("email_assistant_mcp.email_clients.gmail_client", level="ERROR") as logs:
            with self.assertRaises(error.URLError):
                self.client._gmail_request("fake_token", "GET", "https://example.com/test")

        # Verify error was logged
        self.assertEqual(len(logs.output), 1)
        log_message = logs.output[0]

        # Verify log contains expected fields
        self.assertIn("duration_ms=", log_message)
        self.assertIn("method=GET", log_message)
        self.assertIn("Gmail request network error", log_message)
        self.assertIn("Connection refused", log_message)


if __name__ == "__main__":
    unittest.main()

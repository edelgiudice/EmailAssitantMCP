"""Unit tests for the Gmail setup helpers."""

from __future__ import annotations

import unittest
from unittest import mock

from email_assistant_mcp.config import GmailOAuthConfig
from email_assistant_mcp import setup_helpers
from email_assistant_mcp.setup_helpers import (
    GMAIL_SCOPES,
    complete_gmail_setup,
)


class CompleteGmailSetupTests(unittest.TestCase):
    def test_runs_oauth_flow_and_returns_config(self) -> None:
        flow_cls = mock.Mock()
        flow_instance = flow_cls.from_client_config.return_value
        credentials = mock.Mock(refresh_token="test-fake-refresh-token-not-real-12345")
        flow_instance.run_local_server.return_value = credentials
        with mock.patch.object(setup_helpers, "InstalledAppFlow", flow_cls):
            config = complete_gmail_setup(
                email_address="user@example.com",
                display_name="User",
                client_id="client-id",
                client_secret="test-fake-client-secret-not-real-xyz",
                open_browser=False,
            )

        self.assertIsInstance(config, GmailOAuthConfig)
        self.assertEqual(config.refresh_token, "test-fake-refresh-token-not-real-12345")
        self.assertEqual(config.client_id, "client-id")
        flow_cls.from_client_config.assert_called_once()
        args, kwargs = flow_cls.from_client_config.call_args
        oauth_config = args[0]
        self.assertEqual(oauth_config["installed"]["client_id"], "client-id")
        self.assertEqual(oauth_config["installed"]["client_secret"], "test-fake-client-secret-not-real-xyz")
        self.assertEqual(kwargs["scopes"], GMAIL_SCOPES)
        flow_instance.run_local_server.assert_called_once_with(
            host="127.0.0.1",
            port=0,
            authorization_prompt_message=mock.ANY,
            success_message="Authorization complete. You may close this tab.",
            open_browser=False,
            access_type="offline",
            prompt="consent",
        )

    def test_raises_when_refresh_token_missing(self) -> None:
        flow_cls = mock.Mock()
        flow_instance = flow_cls.from_client_config.return_value
        credentials = mock.Mock(refresh_token=None)
        flow_instance.run_local_server.return_value = credentials
        with mock.patch.object(setup_helpers, "InstalledAppFlow", flow_cls):
            with self.assertRaises(RuntimeError) as cm:
                complete_gmail_setup(
                    email_address="user@example.com",
                    display_name=None,
                    client_id="client-id",
                    client_secret="test-fake-client-secret-not-real-xyz",
                    open_browser=False,
                )

        self.assertIn("did not return a refresh token", str(cm.exception))


if __name__ == "__main__":
    unittest.main()

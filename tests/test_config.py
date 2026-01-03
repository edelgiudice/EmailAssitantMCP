"""Unit tests for the provider configuration dataclasses and helpers."""

from __future__ import annotations

import unittest

from typing import cast

from email_assistant_mcp.config import (
    GmailOAuthConfig,
    email_config_from_dict,
    email_config_to_dict,
)


class EmailConfigFromDictTests(unittest.TestCase):
    def test_returns_gmail_config_for_gmail_payload(self) -> None:
        payload = {
            "provider": "gmail",
            "email_address": "user@example.com",
            "display_name": "User",
            "refresh_token": "test-fake-refresh-token-not-real-12345",
            "client_id": "test-fake-client-id-not-real-abcde",
            "client_secret": "test-fake-client-secret-not-real-67890",
            "token_uri": "https://oauth.example/token",
            "imap_host": "imap.example.com",
            "imap_port": 1993,
            "smtp_host": "smtp.example.com",
            "smtp_port": 1587,
        }

        config = email_config_from_dict(payload)

        self.assertIsInstance(config, GmailOAuthConfig)
        gmail = cast(GmailOAuthConfig, config)
        self.assertEqual(gmail.email_address, "user@example.com")
        self.assertEqual(gmail.display_name, "User")
        self.assertEqual(gmail.refresh_token, "test-fake-refresh-token-not-real-12345")
        self.assertEqual(gmail.client_id, "test-fake-client-id-not-real-abcde")
        self.assertEqual(gmail.smtp_host, "smtp.example.com")

    def test_raises_error_for_unknown_provider(self) -> None:
        with self.assertRaises(ValueError) as cm:
            email_config_from_dict({"provider": "imap"})

        self.assertIn("Unsupported email provider", str(cm.exception))

    def test_raises_error_for_missing_provider(self) -> None:
        with self.assertRaises(ValueError) as cm:
            email_config_from_dict({})

        self.assertIn("Missing required field 'provider'", str(cm.exception))

    def test_raises_error_for_invalid_email_format(self) -> None:
        with self.assertRaises(ValueError) as cm:
            email_config_from_dict({
                "provider": "gmail",
                "email_address": "not-an-email"
            })

        self.assertIn("invalid email format", str(cm.exception))

    def test_raises_error_for_port_as_string(self) -> None:
        with self.assertRaises(ValueError) as cm:
            email_config_from_dict({
                "provider": "gmail",
                "email_address": "user@example.com",
                "imap_port": "993"
            })

        self.assertIn("must be an integer", str(cm.exception))

    def test_raises_error_for_port_out_of_range_too_high(self) -> None:
        with self.assertRaises(ValueError) as cm:
            email_config_from_dict({
                "provider": "gmail",
                "email_address": "user@example.com",
                "imap_port": 99999
            })

        self.assertIn("must be between 1 and 65535", str(cm.exception))

    def test_raises_error_for_port_out_of_range_zero(self) -> None:
        with self.assertRaises(ValueError) as cm:
            email_config_from_dict({
                "provider": "gmail",
                "email_address": "user@example.com",
                "smtp_port": 0
            })

        self.assertIn("must be between 1 and 65535", str(cm.exception))

    def test_raises_error_for_empty_email_address(self) -> None:
        with self.assertRaises(ValueError) as cm:
            email_config_from_dict({
                "provider": "gmail",
                "email_address": ""
            })

        self.assertIn("must be a non-empty string", str(cm.exception))

    def test_raises_error_for_wrong_type_email_address(self) -> None:
        with self.assertRaises(ValueError) as cm:
            email_config_from_dict({
                "provider": "gmail",
                "email_address": 12345
            })

        self.assertIn("must be a non-empty string", str(cm.exception))

    def test_accepts_empty_refresh_token(self) -> None:
        """Empty refresh_token is allowed for incomplete configs."""
        payload = {
            "provider": "gmail",
            "email_address": "user@example.com",
            "refresh_token": "",
        }

        config = email_config_from_dict(payload)

        self.assertIsInstance(config, GmailOAuthConfig)
        self.assertEqual(config.refresh_token, "")

    def test_accepts_empty_client_id(self) -> None:
        """Empty client_id is allowed for incomplete configs."""
        payload = {
            "provider": "gmail",
            "email_address": "user@example.com",
            "client_id": "",
        }

        config = email_config_from_dict(payload)

        self.assertIsInstance(config, GmailOAuthConfig)
        self.assertEqual(config.client_id, "")

    def test_accepts_empty_client_secret(self) -> None:
        """Empty client_secret is allowed for incomplete configs."""
        payload = {
            "provider": "gmail",
            "email_address": "user@example.com",
            "client_secret": "",
        }

        config = email_config_from_dict(payload)

        self.assertIsInstance(config, GmailOAuthConfig)
        self.assertEqual(config.client_secret, "")

    def test_accepts_missing_refresh_token(self) -> None:
        """Missing refresh_token uses default empty value."""
        payload = {
            "provider": "gmail",
            "email_address": "user@example.com",
        }

        config = email_config_from_dict(payload)

        self.assertIsInstance(config, GmailOAuthConfig)
        self.assertEqual(config.refresh_token, "")

    def test_raises_error_for_non_string_refresh_token(self) -> None:
        """Non-string refresh_token should raise validation error."""
        with self.assertRaises(ValueError) as cm:
            email_config_from_dict({
                "provider": "gmail",
                "email_address": "user@example.com",
                "refresh_token": 12345
            })

        self.assertIn("must be a string", str(cm.exception))

    def test_raises_error_for_non_string_client_id(self) -> None:
        """Non-string client_id should raise validation error."""
        with self.assertRaises(ValueError) as cm:
            email_config_from_dict({
                "provider": "gmail",
                "email_address": "user@example.com",
                "client_id": ["not", "a", "string"]
            })

        self.assertIn("must be a string", str(cm.exception))

    def test_raises_error_for_non_string_client_secret(self) -> None:
        """Non-string client_secret should raise validation error."""
        with self.assertRaises(ValueError) as cm:
            email_config_from_dict({
                "provider": "gmail",
                "email_address": "user@example.com",
                "client_secret": None
            })

        self.assertIn("must be a string", str(cm.exception))


class EmailConfigToDictTests(unittest.TestCase):
    def test_serializes_gmail_config_to_plain_dict(self) -> None:
        config = GmailOAuthConfig(
            email_address="user@example.com",
            display_name="User",
            refresh_token="test-fake-refresh-token-not-real-12345",
            client_id="test-fake-client-id-not-real-abcde",
            client_secret="test-fake-client-secret-not-real-67890",
            token_uri="https://custom/token",
            imap_host="imap.custom.example",
            imap_port=1993,
            smtp_host="smtp.custom.example",
            smtp_port=1587,
        )

        result = email_config_to_dict(config)

        self.assertEqual(
            result,
            {
                "email_address": "user@example.com",
                "display_name": "User",
                "provider": "gmail",
                "refresh_token": "test-fake-refresh-token-not-real-12345",
                "client_id": "test-fake-client-id-not-real-abcde",
                "client_secret": "test-fake-client-secret-not-real-67890",
                "token_uri": "https://custom/token",
                "imap_host": "imap.custom.example",
                "imap_port": 1993,
                "smtp_host": "smtp.custom.example",
                "smtp_port": 1587,
            },
        )


if __name__ == "__main__":
    unittest.main()

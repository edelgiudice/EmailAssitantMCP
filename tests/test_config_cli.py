"""Unit tests for the credential management helper CLI."""

from __future__ import annotations

import sys
import unittest
from unittest import mock

from email_assistant_mcp.config_cli import (
    build_parser,
    delete_config,
    describe_config,
    list_configs,
    main,
    prompt,
    run_gmail_flow,
)
from email_assistant_mcp.credential_store import CredentialNotFoundError


class BuildParserTests(unittest.TestCase):
    def test_requires_subcommand(self) -> None:
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args([])

    def test_gmail_command_defaults_to_open_browser(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["add-gmail", "work-account"])

        self.assertTrue(args.open_browser)

    def test_gmail_command_supports_disabling_browser(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["add-gmail", "work-account", "--no-open-browser"])

        self.assertFalse(args.open_browser)


class PromptTests(unittest.TestCase):
    @mock.patch("builtins.input", return_value="  value  ")
    def test_returns_stripped_value_for_standard_input(self, mock_input: mock.MagicMock) -> None:
        result = prompt("Field name")

        self.assertEqual(result, "value")
        mock_input.assert_called_once_with("Field name: ")

    @mock.patch("email_assistant_mcp.config_cli.getpass", return_value="s3cr3t")
    def test_uses_getpass_for_secret_values(self, mock_getpass: mock.MagicMock) -> None:
        result = prompt("Password", secret=True)

        self.assertEqual(result, "s3cr3t")
        mock_getpass.assert_called_once_with("Password: ")

    @mock.patch("builtins.print")
    @mock.patch("builtins.input", side_effect=["", "user"])
    def test_repeats_prompt_until_value_entered(
        self,
        mock_input: mock.MagicMock,
        mock_print: mock.MagicMock,
    ) -> None:
        result = prompt("Username")

        self.assertEqual(result, "user")
        self.assertEqual(mock_input.call_count, 2)
        mock_print.assert_called_once_with("This field is required.")

    @mock.patch("builtins.input", return_value="")
    def test_optional_prompt_accepts_empty_value(self, mock_input: mock.MagicMock) -> None:
        result = prompt("Display name", optional=True)

        self.assertEqual(result, "")
        mock_input.assert_called_once()


class RunGmailFlowTests(unittest.TestCase):
    @mock.patch("email_assistant_mcp.config_cli.CredentialStore.default")
    @mock.patch("email_assistant_mcp.config_cli.complete_gmail_setup")
    @mock.patch("email_assistant_mcp.config_cli.prompt")
    def test_passes_prompted_values_to_helper(
        self,
        mock_prompt: mock.MagicMock,
        mock_setup: mock.MagicMock,
        mock_store_factory: mock.MagicMock,
    ) -> None:
        mock_prompt.side_effect = ["user@example.com", "", "client", "secret"]

        run_gmail_flow("gmail-config", open_browser=False)

        mock_setup.assert_called_once_with(
            email_address="user@example.com",
            display_name=None,
            client_id="client",
            client_secret="secret",
            open_browser=False,
        )

    @mock.patch("email_assistant_mcp.config_cli.CredentialStore.default")
    @mock.patch("email_assistant_mcp.config_cli.complete_gmail_setup")
    @mock.patch("email_assistant_mcp.config_cli.prompt")
    def test_saves_config_returned_by_helper(
        self,
        mock_prompt: mock.MagicMock,
        mock_setup: mock.MagicMock,
        mock_store_factory: mock.MagicMock,
    ) -> None:
        mock_prompt.side_effect = ["user@example.com", "User", "client", "secret"]
        config = object()
        mock_setup.return_value = config

        run_gmail_flow("gmail-config", open_browser=True)

        mock_store_factory.return_value.save_config.assert_called_once_with("gmail-config", config)


class DescribeConfigTests(unittest.TestCase):
    @mock.patch("builtins.print")
    @mock.patch("email_assistant_mcp.config_cli.CredentialStore.default")
    def test_prints_metadata_fields(
        self,
        mock_store_factory: mock.MagicMock,
        mock_print: mock.MagicMock,
    ) -> None:
        mock_store_factory.return_value.describe_config.return_value = {
            "config_id": "demo",
            "provider": "gmail",
            "email_address": "user@example.com",
            "display_name": "User",
        }

        describe_config("demo")

        mock_print.assert_has_calls(
            [
                mock.call("config_id: demo"),
                mock.call("provider: gmail"),
                mock.call("email_address: user@example.com"),
                mock.call("display_name: User"),
            ]
        )

    @mock.patch("builtins.print")
    @mock.patch("email_assistant_mcp.config_cli.CredentialStore.default")
    def test_missing_config_exits_with_error(
        self,
        mock_store_factory: mock.MagicMock,
        mock_print: mock.MagicMock,
    ) -> None:
        mock_store_factory.return_value.describe_config.side_effect = CredentialNotFoundError("demo")

        with self.assertRaises(SystemExit) as cm:
            describe_config("demo")

        self.assertEqual(cm.exception.code, 1)
        mock_print.assert_called_once_with("Config 'demo' not found.", file=sys.stderr)


class ListConfigsTests(unittest.TestCase):
    @mock.patch("builtins.print")
    @mock.patch("email_assistant_mcp.config_cli.CredentialStore.default")
    def test_prints_message_when_store_empty(
        self,
        mock_store_factory: mock.MagicMock,
        mock_print: mock.MagicMock,
    ) -> None:
        mock_store_factory.return_value.list_config_ids.return_value = []

        list_configs()

        mock_print.assert_called_once_with("No configurations stored yet.")

    @mock.patch("builtins.print")
    @mock.patch("email_assistant_mcp.config_cli.CredentialStore.default")
    def test_prints_each_config_summary(
        self,
        mock_store_factory: mock.MagicMock,
        mock_print: mock.MagicMock,
    ) -> None:
        store = mock_store_factory.return_value
        store.list_config_ids.return_value = ["config-a", "config-b"]
        store.describe_config.side_effect = [
            {
                "provider": "gmail",
                "email_address": "a@example.com",
            },
            {
                "provider": "gmail",
                "email_address": "b@example.com",
            },
        ]

        list_configs()

        self.assertEqual(
            store.describe_config.call_args_list,
            [mock.call("config-a"), mock.call("config-b")],
        )
        mock_print.assert_has_calls(
            [
                mock.call("- config-a: gmail (a@example.com)"),
                mock.call("- config-b: gmail (b@example.com)"),
            ]
        )


class DeleteConfigTests(unittest.TestCase):
    @mock.patch("email_assistant_mcp.config_cli.CredentialStore.default")
    def test_invokes_store_delete(self, mock_store_factory: mock.MagicMock) -> None:
        delete_config("obsolete")

        mock_store_factory.return_value.delete_config.assert_called_once_with("obsolete")

    @mock.patch("builtins.print")
    @mock.patch("email_assistant_mcp.config_cli.CredentialStore.default")
    def test_missing_config_exits_with_error(
        self,
        mock_store_factory: mock.MagicMock,
        mock_print: mock.MagicMock,
    ) -> None:
        mock_store_factory.return_value.delete_config.side_effect = CredentialNotFoundError("obsolete")

        with self.assertRaises(SystemExit) as cm:
            delete_config("obsolete")

        self.assertEqual(cm.exception.code, 1)
        mock_print.assert_called_once_with("Config 'obsolete' not found.", file=sys.stderr)

    @mock.patch("builtins.print")
    @mock.patch("email_assistant_mcp.config_cli.CredentialStore.default")
    def test_prints_confirmation_on_success(
        self,
        mock_store_factory: mock.MagicMock,
        mock_print: mock.MagicMock,
    ) -> None:
        delete_config("obsolete")

        mock_print.assert_called_once_with("Deleted config 'obsolete'.")


class MainTests(unittest.TestCase):
    @mock.patch("email_assistant_mcp.config_cli.run_gmail_flow")
    def test_dispatches_gmail_flow(self, mock_flow: mock.MagicMock) -> None:
        main(["add-gmail", "demo"])

        mock_flow.assert_called_once_with("demo", True)

    @mock.patch("email_assistant_mcp.config_cli.list_configs")
    def test_dispatches_list_command(self, mock_list: mock.MagicMock) -> None:
        main(["list"])

        mock_list.assert_called_once_with()

    @mock.patch("email_assistant_mcp.config_cli.delete_config")
    def test_dispatches_delete_command(self, mock_delete: mock.MagicMock) -> None:
        main(["delete", "demo"])

        mock_delete.assert_called_once_with("demo")

    @mock.patch("email_assistant_mcp.config_cli.describe_config")
    def test_dispatches_describe_command(self, mock_describe: mock.MagicMock) -> None:
        main(["describe", "demo"])

        mock_describe.assert_called_once_with("demo")

    @mock.patch("email_assistant_mcp.config_cli.list_configs")
    def test_returns_zero_on_success(self, mock_list: mock.MagicMock) -> None:
        exit_code = main(["list"])

        mock_list.assert_called_once()
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()

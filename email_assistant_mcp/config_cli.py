"""Helper CLI to manage provider credentials stored on disk."""

from __future__ import annotations

import argparse
import sys
from getpass import getpass
from typing import Sequence

from .credential_store import CredentialNotFoundError, CredentialStore
from .setup_helpers import complete_gmail_setup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage stored email account configurations."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_common = argparse.ArgumentParser(add_help=False)
    add_common.add_argument(
        "config_id",
        help="Unique identifier used to reference this configuration",
    )

    gmail_parser = subparsers.add_parser(
        "add-gmail",
        help="Launch the OAuth helper to capture a Gmail refresh token",
        parents=[add_common],
    )
    gmail_parser.add_argument(
        "--open-browser",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Automatically open Google's consent screen when starting the flow",
    )

    subparsers.add_parser("list", help="Show all stored configuration IDs")

    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete a stored configuration",
    )
    delete_parser.add_argument("config_id")

    subparsers.add_parser(
        "describe",
        help="Show metadata (no secrets) for a stored configuration",
    ).add_argument("config_id")

    return parser


def prompt(text: str, secret: bool = False, optional: bool = False) -> str:
    """Prompt user input with optional secret handling."""
    while True:
        value = getpass(f"{text}: ") if secret else input(f"{text}: ").strip()
        if value or optional:
            return value
        print("This field is required.")


def run_gmail_flow(config_id: str, open_browser: bool) -> None:
    print("Configuring Gmail account")
    email_address = prompt("Email address")
    display_name = prompt("Display name (optional)", optional=True) or None
    client_id = prompt("Google OAuth client ID")
    client_secret = prompt("Google OAuth client secret", secret=True)
    config = complete_gmail_setup(
        email_address=email_address,
        display_name=display_name,
        client_id=client_id,
        client_secret=client_secret,
        open_browser=open_browser,
    )
    CredentialStore.default().save_config(config_id, config)
    print(f"Stored Gmail config '{config_id}' for {email_address}.")


def describe_config(config_id: str) -> None:
    store = CredentialStore.default()
    try:
        metadata = store.describe_config(config_id)
    except CredentialNotFoundError:
        print(f"Config '{config_id}' not found.", file=sys.stderr)
        raise SystemExit(1) from None
    for key, value in metadata.items():
        print(f"{key}: {value}")


def list_configs() -> None:
    store = CredentialStore.default()
    config_ids = store.list_config_ids()
    if not config_ids:
        print("No configurations stored yet.")
        return
    for config_id in config_ids:
        metadata = store.describe_config(config_id)
        print(f"- {config_id}: {metadata['provider']} ({metadata['email_address']})")


def delete_config(config_id: str) -> None:
    store = CredentialStore.default()
    try:
        store.delete_config(config_id)
    except CredentialNotFoundError:
        print(f"Config '{config_id}' not found.", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"Deleted config '{config_id}'.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command
    if command == "add-gmail":
        run_gmail_flow(args.config_id, args.open_browser)
    elif command == "list":
        list_configs()
    elif command == "delete":
        delete_config(args.config_id)
    elif command == "describe":
        describe_config(args.config_id)
    else:
        parser.error(f"Unknown command {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

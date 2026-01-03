"""Bootstrap tool registrations for the FastMCP email assistant."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..logging_redaction import redact_email
from ..setup_helpers import complete_gmail_setup

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..credential_store import CredentialStore


def register_bootstrap_tools(server: FastMCP, credential_store: CredentialStore) -> None:
    """Attach the initial configuration and setup tools to the FastMCP server."""
    active_config_id: str | None = None

    @server.tool(
        name="health_check",
        description="Verify that the email assistant server is reachable.",
    )
    async def health_check() -> str:
        logger.info("Health check requested")
        return "email assistant server ready"

    @server.tool(
        name="list_email_accounts",
        description="Return metadata for every stored email configuration (no secrets).",
    )
    async def list_email_accounts() -> list[dict[str, str | None]]:
        logger.info("Listing email accounts")
        ids = credential_store.list_config_ids()
        logger.debug("Found email accounts | count=%d", len(ids))
        return [credential_store.describe_config(config_id) for config_id in ids]

    @server.tool(
        name="activate_email_account",
        description="Select which stored account should be used for follow-up actions.",
    )
    async def activate_email_account(config_id: str) -> str:
        nonlocal active_config_id
        logger.info("Activating email account | config_id=%s", config_id)
        metadata = credential_store.describe_config(config_id)
        active_config_id = config_id
        logger.info(
            "Email account activated | config_id=%s provider=%s email=%s",
            config_id,
            metadata.get("provider"),
            metadata.get("email_address", "unknown")  # Already redacted by describe_config()
        )
        return f"Activated {metadata['provider']} account for {metadata['email_address']}"

    @server.tool(
        name="current_email_account",
        description="Return the currently-selected account metadata if any.",
    )
    async def current_email_account() -> dict[str, str | None]:
        logger.debug("Checking current email account")
        if not active_config_id:
            logger.debug("No active email account")
            return {"status": "inactive"}
        logger.debug("Current active account | config_id=%s", active_config_id)
        metadata = credential_store.describe_config(active_config_id)
        metadata["status"] = "active"
        return metadata

    @server.tool(
        name="setup_gmail_account",
        description=(
            "Launch the Gmail OAuth consent flow and store the resulting refresh token. "
            "Requires the Google OAuth client ID and secret created in the Cloud Console."
        ),
    )
    async def setup_gmail_account(
        config_id: str,
        email_address: str,
        client_id: str,
        client_secret: str,
        display_name: str | None = None,
        open_browser: bool = True,
    ) -> str:
        logger.info(
            "Starting Gmail account setup | config_id=%s email=%s",
            config_id,
            redact_email(email_address)
        )
        try:
            config = complete_gmail_setup(
                email_address=email_address,
                display_name=display_name,
                client_id=client_id,
                client_secret=client_secret,
                open_browser=open_browser,
            )
            credential_store.save_config(config_id, config)
            logger.info(
                "Gmail account setup completed | config_id=%s email=%s",
                config_id,
                redact_email(email_address)
            )
            return f"Stored Gmail config '{config_id}' for {email_address}."
        except Exception as e:
            logger.error(
                "Gmail account setup failed | config_id=%s email=%s error=%s",
                config_id,
                redact_email(email_address),
                str(e)
            )
            raise

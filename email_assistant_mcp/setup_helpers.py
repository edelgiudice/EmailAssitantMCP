"""Utility functions to provision provider credentials."""

from __future__ import annotations

import webbrowser
from typing import Final

from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore

from .config import GmailOAuthConfig

GMAIL_SCOPES: Final = ("https://mail.google.com/",)


def complete_gmail_setup(
    *,
    email_address: str,
    display_name: str | None,
    client_id: str,
    client_secret: str,
    open_browser: bool = True,
) -> GmailOAuthConfig:
    """Run the OAuth consent flow and return a populated Gmail config."""
    oauth_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = InstalledAppFlow.from_client_config(oauth_config, scopes=GMAIL_SCOPES)
    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        authorization_prompt_message=(
            "Authorize Email Assistant MCP to access Gmail then return here."
        ),
        success_message="Authorization complete. You may close this tab.",
        open_browser=open_browser,
        access_type="offline",
        prompt="consent",
    )
    refresh_token = credentials.refresh_token
    if not refresh_token:
        msg = "Google did not return a refresh token; ensure 'Desktop' client type."
        raise RuntimeError(msg)
    return GmailOAuthConfig(
        email_address=email_address,
        display_name=display_name,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )

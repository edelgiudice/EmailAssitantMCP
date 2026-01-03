"""Operational email tools with backward-compatible folder helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .folder import FolderTools, register_folder_tools

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..credential_store import CredentialStore


def register_email_ops_tools(
    server: FastMCP,
    credential_store: CredentialStore,
    *,
    email_ops: FolderTools | None = None,
) -> None:
    """Attach operational email tools to the FastMCP server."""
    register_folder_tools(
        server,
        credential_store,
        folder_tools=email_ops,
    )

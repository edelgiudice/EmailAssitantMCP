"""Folder-related email tools."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING
from urllib.parse import quote

from ..config import EmailProviderConfig
from ..email_clients import EmailClient, GmailClient
from ..logging_redaction import redact_email
from .base import ProviderBackedToolSet

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..credential_store import CredentialStore

LOGGER = logging.getLogger(__name__)

DEFAULT_FOLDER_TEMPLATES: dict[str, list[dict[str, str]]] = {
    GmailClient.provider: GmailClient.default_folders(),
}

DEFAULT_FALLBACK_FOLDERS: list[dict[str, str]] = [
    {"id": "INBOX", "name": "Inbox", "type": "system"},
    {"id": "SENT", "name": "Sent", "type": "system"},
    {"id": "DRAFT", "name": "Drafts", "type": "system"},
]


class FolderTools(ProviderBackedToolSet):
    """High-level coordinator for email folder operations."""

    def __init__(
        self,
        *,
        provider_clients: Mapping[str, EmailClient] | None = None,
        folder_templates: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
        fallback_folders: Sequence[Mapping[str, str]] | None = None,
    ) -> None:
        """Initialize FolderTools with provider clients and folder templates.

        Args:
            provider_clients: Optional mapping of provider names to EmailClient instances
            folder_templates: Optional mapping of provider names to folder definitions
            fallback_folders: Optional list of fallback folders when provider unavailable
        """
        super().__init__(provider_clients=provider_clients)
        templates = folder_templates or DEFAULT_FOLDER_TEMPLATES
        self._folder_templates = {
            key.lower(): self._clone_entries(entries)
            for key, entries in templates.items()
        }
        fallback = fallback_folders or DEFAULT_FALLBACK_FOLDERS
        self._fallback_folders = self._clone_entries(fallback)

    def register(self, server: FastMCP, credential_store: CredentialStore) -> None:
        """Attach folder tools to the FastMCP server."""

        @server.tool(
            name="list_email_folders",
            description=(
                "Return the standard folders for a stored email configuration. "
                "The folders are exposed as a resource keyed by the email address."
            ),
        )
        async def list_email_folders(config_id: str) -> dict[str, str | int]:
            LOGGER.info("Listing email folders | config_id=%s", config_id)
            config = credential_store.get_config(config_id)
            email_address = getattr(config, "email_address", None)
            if not email_address:
                msg = f"Config '{config_id}' is missing the email address metadata."
                LOGGER.error("Missing email address in config | config_id=%s", config_id)
                raise ValueError(msg)

            provider = getattr(config, "provider", None) or "unknown"
            LOGGER.debug(
                "Fetching folders | config_id=%s provider=%s email=%s",
                config_id,
                provider,
                redact_email(email_address)
            )
            resource_uri, folders = self._sync_folder_resource(
                server=server,
                config=config,
                config_id=config_id,
                email_address=email_address,
                provider=provider,
            )
            LOGGER.info(
                "Folders retrieved | config_id=%s provider=%s folder_count=%d",
                config_id,
                provider,
                len(folders)
            )
            return {
                "resource_uri": resource_uri,
                "email_address": email_address,
                "provider": provider,
                "folder_count": len(folders),
            }

        @server.tool(
            name="create_email_folder",
            description=(
                "Create a folder (label) for a stored email configuration. "
                "Supports optional parent folders when the provider allows nesting."
            ),
        )
        async def create_email_folder(
            config_id: str,
            folder_name: str,
            parent_folder: str | None = None,
        ) -> dict[str, object]:
            LOGGER.info(
                "Creating email folder | config_id=%s folder_name=%s parent=%s",
                config_id,
                folder_name,
                parent_folder or "none"
            )
            folder_name = (folder_name or "").strip()
            if not folder_name:
                msg = "A folder name is required."
                LOGGER.error("Folder creation failed - empty name | config_id=%s", config_id)
                raise ValueError(msg)
            config = credential_store.get_config(config_id)
            email_address = getattr(config, "email_address", None)
            if not email_address:
                msg = f"Config '{config_id}' is missing the email address metadata."
                LOGGER.error("Missing email address in config | config_id=%s", config_id)
                raise ValueError(msg)
            provider = getattr(config, "provider", None) or "unknown"

            try:
                created_folder = self._create_provider_folder(
                    config,
                    folder_name,
                    parent_folder=parent_folder,
                )
                LOGGER.info(
                    "Folder created | config_id=%s folder_name=%s folder_id=%s",
                    config_id,
                    folder_name,
                    created_folder.get("id", "unknown")
                )
                # Invalidate folder cache since we just created a new folder
                self._invalidate_folder_cache(config_id, provider)
            except Exception as e:
                LOGGER.error(
                    "Folder creation failed | config_id=%s folder_name=%s error=%s",
                    config_id,
                    folder_name,
                    str(e)
                )
                raise

            resource_uri, folders = self._sync_folder_resource(
                server=server,
                config=config,
                config_id=config_id,
                email_address=email_address,
                provider=provider,
            )
            return {
                "config_id": config_id,
                "email_address": email_address,
                "provider": provider,
                "folder": created_folder,
                "resource_uri": resource_uri,
                "folder_count": len(folders),
            }

    def _folders_for_provider(self, provider: str | None) -> list[dict[str, str]]:
        """Get folder template list for a provider.

        Args:
            provider: Provider name (e.g., 'gmail')

        Returns:
            List of folder dictionaries from template or fallback folders
        """
        template = self._folder_templates.get(
            self._provider_key(provider),
            self._fallback_folders,
        )
        return self._clone_entries(template)

    @staticmethod
    def _resource_uri(email_address: str) -> str:
        safe_address = quote(email_address, safe="")
        return f"resource://email-folders/{safe_address}"

    def _sync_folder_resource(
        self,
        *,
        server: FastMCP,
        config: EmailProviderConfig,
        config_id: str,
        email_address: str,
        provider: str,
    ) -> tuple[str, list[dict[str, str]]]:
        """Discover folders and ensure the server resource mirrors the result."""
        folders = self._discover_provider_folders(config, config_id)
        resource_uri = self._resource_uri(email_address)
        self._register_folder_resource(
            server=server,
            resource_uri=resource_uri,
            email_address=email_address,
            payload={
                "config_id": config_id,
                "email_address": email_address,
                "provider": provider,
                "folders": folders,
            },
        )
        return resource_uri, folders

    def _discover_provider_folders(
        self,
        config: EmailProviderConfig,
        config_id: str | None = None,
    ) -> list[dict[str, str]]:
        provider = getattr(config, "provider", None)
        provider_key = self._provider_key(provider)
        client = self._client_for_provider(provider)
        if not client:
            LOGGER.debug("No client for provider, using templates | provider=%s", provider_key or "unknown")
            return self._folders_for_provider(provider_key)
        try:
            LOGGER.debug("Discovering folders from provider | provider=%s", provider_key)
            # Use cached folders if config_id is provided
            if config_id:
                folders = self._get_folders_cached(client, config, config_id)
            else:
                folders = client.list_folders(config)
            LOGGER.debug("Folders discovered | provider=%s count=%d", provider_key, len(folders))
            return folders
        except Exception as exc:  # pragma: no cover - network side effects
            LOGGER.warning(
                "Falling back to static folders | provider=%s error=%s",
                provider_key or "unknown",
                str(exc)
            )
            return self._folders_for_provider(provider_key)

    def _create_provider_folder(
        self,
        config: EmailProviderConfig,
        folder_name: str,
        *,
        parent_folder: str | None = None,
    ) -> dict[str, str]:
        provider = getattr(config, "provider", None)
        provider_key = self._provider_key(provider)
        client = self._client_for_provider(provider)
        if not client or not client.supports_folder_creation:
            msg = f"Folder creation is not supported for provider '{provider_key or 'unknown'}'."
            raise ValueError(msg)
        return client.create_folder(config, folder_name, parent_folder)

    def _register_folder_resource(
        self,
        *,
        server: FastMCP,
        resource_uri: str,
        email_address: str,
        payload: dict[str, object],
    ) -> None:
        """Create or update a resource that returns the folder payload."""

        def _read_resource() -> str:
            return json.dumps(payload, indent=2)

        server.resource(
            resource_uri,
            name=email_address,
            description=f"Available folders for {email_address}",
            mime_type="application/json",
        )(_read_resource)

def register_folder_tools(
    server: FastMCP,
    credential_store: CredentialStore,
    *,
    folder_tools: FolderTools | None = None,
) -> None:
    """Attach folder tools to the FastMCP server."""

    if folder_tools is None:
        folder_tools = FolderTools()

    folder_tools.register(server, credential_store)

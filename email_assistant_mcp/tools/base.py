"""Shared helpers for provider-backed email tools."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from cachetools import TTLCache
from ..email_clients import EmailClient, GmailClient

logger = logging.getLogger(__name__)


class ProviderBackedToolSet:
    """Base class for tool sets that rely on provider-specific clients."""

    def __init__(self, *, provider_clients: Mapping[str, EmailClient] | None = None) -> None:
        """Initialize ProviderBackedToolSet with email clients.

        Args:
            provider_clients: Optional mapping of provider names to EmailClient instances.
                            Defaults to built-in Gmail client if not provided.
        """
        resolved_clients = provider_clients or self._default_provider_clients()
        self._provider_clients = {
            key.lower(): client for key, client in resolved_clients.items()
        }
        # Folder cache with 5 minute TTL, keyed by config_id:provider
        self._folder_cache: TTLCache[str, list[dict[str, Any]]] = TTLCache(maxsize=100, ttl=300)

    @staticmethod
    def _default_provider_clients() -> dict[str, EmailClient]:
        """Get default provider client mapping.

        Returns:
            Dictionary mapping provider names to EmailClient instances
        """
        return {
            GmailClient.provider: GmailClient(),
        }

    @staticmethod
    def _clone_entries(entries: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
        """Clone a sequence of mappings into a list of dicts.

        Args:
            entries: Sequence of string-to-string mappings

        Returns:
            List of dictionaries copied from input mappings
        """
        return [dict(entry) for entry in entries]

    @staticmethod
    def _provider_key(provider: str | None) -> str:
        """Normalize provider name to lowercase.

        Args:
            provider: Provider name or None

        Returns:
            Lowercase provider name or empty string
        """
        return (provider or "").lower()

    def _client_for_provider(self, provider: str | None) -> EmailClient | None:
        """Get email client for a provider.

        Args:
            provider: Provider name (e.g., 'gmail')

        Returns:
            EmailClient instance or None if provider not found
        """
        return self._provider_clients.get(self._provider_key(provider))

    def _get_folders_cached(
        self,
        client: EmailClient,
        config: Any,
        config_id: str,
    ) -> list[dict[str, Any]]:
        """Get folders with caching to reduce API calls.

        Args:
            client: Email client instance
            config: Email provider configuration
            config_id: Configuration identifier

        Returns:
            List of folder dictionaries

        Note:
            Folders are cached for 5 minutes (default TTL). This significantly
            reduces API calls in workflows with multiple operations.
        """
        provider = getattr(config, "provider", None) or "unknown"
        cache_key = f"{config_id}:{provider}"

        # Check cache
        cached_folders = self._folder_cache.get(cache_key)
        if cached_folders is not None:
            logger.debug(
                "Using cached folders | config_id=%s provider=%s",
                config_id,
                provider
            )
            return cached_folders

        # Cache miss or expired - fetch from provider
        logger.debug("Fetching folders from provider | config_id=%s provider=%s", config_id, provider)
        folders = client.list_folders(config)
        self._folder_cache[cache_key] = folders
        logger.debug(
            "Folders cached | config_id=%s provider=%s folder_count=%d",
            config_id,
            provider,
            len(folders)
        )
        return folders

    def _invalidate_folder_cache(self, config_id: str, provider: str | None = None) -> None:
        """Manually invalidate folder cache for a config.

        Args:
            config_id: Configuration identifier
            provider: Optional provider name (invalidates only that config if provided)
        """
        if provider:
            # Invalidate specific config's cache
            cache_key = f"{config_id}:{provider}"
            self._folder_cache.pop(cache_key, None)
            logger.debug("Invalidated folder cache | config_id=%s provider=%s", config_id, provider)
        else:
            # Clear entire cache if provider not specified
            self._folder_cache.clear()
            logger.debug("Invalidated all folder caches | config_id=%s", config_id)

"""Abstract email client interface used by the operational tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from ..config import EmailProviderConfig


class EmailClient(ABC):
    """Base class describing the folder operations an email provider supports."""

    provider: ClassVar[str]

    @abstractmethod
    def list_folders(self, config: EmailProviderConfig) -> list[dict[str, str]]:
        """Return every folder the provider exposes for the given configuration."""

    @property
    def supports_folder_creation(self) -> bool:
        """Return True when the provider supports folder creation."""
        return False

    def create_folder(
        self,
        config: EmailProviderConfig,
        folder_name: str,
        parent_folder: str | None = None,
    ) -> dict[str, str]:
        """Create a folder for the provider. Concrete clients override this method."""
        del config, folder_name, parent_folder
        msg = f"Folder creation is not supported for provider '{self.provider}'."
        raise NotImplementedError(msg)

    @staticmethod
    @abstractmethod
    def default_folders() -> list[dict[str, str]]:
        """Return the provider's default folder definitions."""

    def create_draft(
        self,
        config: EmailProviderConfig,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Create a provider-specific draft message.

        Providers override this method when they support draft APIs.
        """

        del config, payload
        msg = f"Draft creation is not supported for provider '{self.provider}'."
        raise NotImplementedError(msg)

    def search_messages(
        self,
        config: EmailProviderConfig,
        filters: Mapping[str, Any],
        *,
        max_results: int | None = None,
    ) -> dict[str, Any]:
        """Search for messages and return all results.

        Implementations should handle pagination internally if the provider
        uses paginated APIs. Fetch all pages and combine into a single
        result set, respecting max_results if provided.

        Args:
            config: Provider configuration
            filters: Search filters dict
            max_results: Optional limit on number of results

        Returns:
            Dict containing:
                - messages: List[dict] - All matching messages
                - total_count: int - Number of messages returned
                - truncated: bool - True if limited by max_results
        """
        del config, filters, max_results
        msg = f"Message search is not supported for provider '{self.provider}'."
        raise NotImplementedError(msg)

    def fetch_message_full(
        self,
        config: EmailProviderConfig,
        message_id: str,
    ) -> dict[str, Any]:
        """Return the full contents of a single message."""

        del config, message_id
        msg = f"Full message fetch is not supported for provider '{self.provider}'."
        raise NotImplementedError(msg)

    def batch_move_messages(
        self,
        config: EmailProviderConfig,
        message_operations: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Move multiple messages with different label configurations.

        Args:
            config: Provider configuration
            message_operations: List of operations, each containing:
                - message_id: str
                - add_labels: List[str] (label names or IDs)
                - remove_labels: List[str] (label names or IDs)

        Returns:
            Dict containing:
                - success: List of successfully modified message IDs with final labels
                - failures: List of failed operations with error details
                - total_count: Total operations attempted
                - success_count: Number of successful operations
                - failure_count: Number of failed operations
        """
        del config, message_operations
        msg = f"Batch move is not supported for provider '{self.provider}'."
        raise NotImplementedError(msg)

"""Message-level tools covering drafts, search, fetch, and move flows."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, time, timezone

from ..utils.datetime_utils import parse_iso8601_to_datetime, utc_now
from ..utils.text_utils import strip_html, truncate_text
from typing import TYPE_CHECKING, Any, Mapping, Sequence
from urllib.parse import quote

from ..config import EmailProviderConfig
from ..logging_redaction import redact_email
from .base import ProviderBackedToolSet

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..credential_store import CredentialStore


PREVIEW_CHAR_LIMIT = 2000
SNIPPET_CHAR_LIMIT = 350
MARK_FOR_DELETION_NAME = "mark_for_deletion"




class MessageTools(ProviderBackedToolSet):
    """Coordinate provider-backed message fetching and mutations."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize MessageTools with optional provider clients.

        Args:
            *args: Positional arguments passed to parent ProviderBackedToolSet
            **kwargs: Keyword arguments passed to parent ProviderBackedToolSet
        """
        super().__init__(*args, **kwargs)
        self._resource_cache: dict[str, Any] = {}

    def register(self, server: FastMCP, credential_store: CredentialStore) -> None:
        """Attach the message tool surface to the FastMCP server."""
        self._register_draft_email_tool(server, credential_store)
        self._register_get_emails_tool(server, credential_store)
        self._register_fetch_email_full_tool(server, credential_store)
        self._register_batch_move_emails_tool(server, credential_store)
        self._register_mark_for_deletion_tool(server, credential_store)
        self._register_read_email_resource_tool(server)

    def _register_draft_email_tool(self, server: FastMCP, credential_store: CredentialStore) -> None:
        @server.tool(
            name="draft_email",
            description=(
                "Create an unsent draft for the provided config_id by supplying recipients (at least one of to/cc/bcc), "
                "optional subject, body_text/body_html (one required), attachments, reply/thread references, and custom "
                "metadata. Normalizes addresses, persists the provider draft, and registers a JSON preview resource "
                "containing the rendered body/snippet so the caller can inspect content. Returns provider/draft/message/"
                "thread identifiers plus the preview resource URI and truncated body preview."
            ),
        )
        async def draft_email(
            config_id: str,
            to: Sequence[str] | str,
            *,
            cc: Sequence[str] | str | None = None,
            bcc: Sequence[str] | str | None = None,
            subject: str | None = None,
            body_text: str | None = None,
            body_html: str | None = None,
            in_reply_to: str | None = None,
            thread_id: str | None = None,
            attachments: Sequence[Mapping[str, Any]] | None = None,
            metadata: Mapping[str, Any] | None = None,
        ) -> dict[str, Any]:
            config = credential_store.get_config(config_id)
            provider = getattr(config, "provider", None)
            client = self._require_client(provider)
            to_list = self._normalize_addresses(to)
            cc_list = self._normalize_addresses(cc)
            bcc_list = self._normalize_addresses(bcc)
            if not any((to_list, cc_list, bcc_list)):
                msg = "At least one recipient (to/cc/bcc) is required to draft an email."
                logger.error("Draft validation failed - no recipients | config_id=%s", config_id)
                raise ValueError(msg)
            subject_value = (subject or "").strip()
            if not any(((body_text or "").strip(), (body_html or "").strip())):
                msg = "Either body_text or body_html must be supplied."
                raise ValueError(msg)

            draft_payload = {
                "to": to_list,
                "cc": cc_list,
                "bcc": bcc_list,
                "subject": subject_value,
                "body_text": (body_text or "").strip() or None,
                "body_html": (body_html or "").strip() or None,
                "in_reply_to": (in_reply_to or "").strip() or None,
                "thread_id": (thread_id or "").strip() or None,
                "attachments": list(attachments or []),
                "metadata": dict(metadata or {}),
            }
            result = client.create_draft(config, draft_payload)
            draft_id = result.get("draft_id")
            if not draft_id:
                msg = "Provider did not return a draft identifier."
                logger.error("Draft creation failed - no draft_id returned | config_id=%s", config_id)
                raise RuntimeError(msg)
            preview_source = draft_payload["body_text"] or strip_html(draft_payload["body_html"] or "", strip_whitespace=True)
            body_preview, _ = truncate_text(preview_source, PREVIEW_CHAR_LIMIT, strip=True)
            snippet, _ = truncate_text(preview_source, SNIPPET_CHAR_LIMIT, strip=True)
            resource_uri = self._draft_resource_uri(draft_id)
            payload = {
                "config_id": config_id,
                "provider": provider,
                "draft_id": draft_id,
                "message_id": result.get("message_id"),
                "thread_id": result.get("thread_id"),
                "subject": subject_value,
                "to": to_list,
                "cc": cc_list,
                "bcc": bcc_list,
                "body_preview": body_preview,
                "snippet": snippet,
                "metadata": draft_payload["metadata"],
                "created_at": utc_now().isoformat(),
            }
            self._register_resource(
                server,
                resource_uri=resource_uri,
                name=f"draft/{draft_id}",
                description=f"Draft preview for {draft_id}",
                payload=payload,
            )
            return {
                "draft_id": draft_id,
                "message_id": result.get("message_id"),
                "thread_id": result.get("thread_id"),
                "provider": provider,
                "preview_resource": resource_uri,
                "body_preview": body_preview,
            }

    def _register_get_emails_tool(self, server: FastMCP, credential_store: CredentialStore) -> None:
        @server.tool(
            name="get_emails",
            description=(
                "Search the specified config_id mailbox using optional filters (query, subject, sender, recipient, "
                "folder, ISO-8601 date_from/date_to). Returns ALL matching messages in a single response, up to "
                "max_results limit (default 500). "
                "\n\n"
                "Filters: query (freeform text), subject, sender, recipient, folder, date_from/date_to (ISO-8601). "
                "When no text filters provided, both date_from and date_to are required. "
                "\n\n"
                "max_results: Limit response size (1-1000, default 500). Set truncated=true if limited. "
                "\n\n"
                "Response includes all matching messages, total count, and truncated flag. Use max_results to "
                "control response size for large result sets."
            ),
        )
        async def get_emails(
            config_id: str,
            *,
            query: str | None = None,
            subject: str | None = None,
            sender: str | None = None,
            recipient: str | None = None,
            folder: str | None = None,
            date_from: str | None = None,
            date_to: str | None = None,
            max_results: int | None = None,
        ) -> dict[str, Any]:
            return await self.search_mailbox(
                server,
                credential_store,
                config_id,
                query=query,
                subject=subject,
                sender=sender,
                recipient=recipient,
                folder=folder,
                date_from=date_from,
                date_to=date_to,
                max_results=max_results,
            )

    def _register_fetch_email_full_tool(self, server: FastMCP, credential_store: CredentialStore) -> None:
        @server.tool(
            name="fetch_email_full",
            description=(
                "Given a config_id and provider message_id, download the provider's canonical full payload (all headers, "
                "MIME body parts, attachment metadata). Registers a JSON resource named messages/<id>/full that callers "
                "can read later and returns the provider id, resource URI, and whether attachments are present."
            ),
        )
        async def fetch_email_full(config_id: str, message_id: str) -> dict[str, Any]:
            message_id = (message_id or "").strip()
            if not message_id:
                msg = "message_id is required."
                logger.error("Fetch failed - missing message_id | config_id=%s", config_id)
                raise ValueError(msg)
            config = credential_store.get_config(config_id)
            provider = getattr(config, "provider", None)
            client = self._require_client(provider)
            result = client.fetch_message_full(config, message_id)
            resource_uri = self._full_resource_uri(message_id)
            payload = {
                "config_id": config_id,
                "provider": provider,
                "message_id": message_id,
                "data": result,
                "fetched_at": utc_now().isoformat(),
            }
            self._register_resource(
                server,
                resource_uri=resource_uri,
                name=f"messages/{message_id}/full",
                description=f"Full message payload for {message_id}",
                payload=payload,
            )
            return {
                "message_id": message_id,
                "provider": provider,
                "resource_uri": resource_uri,
                "has_attachments": bool(result.get("attachments")),
            }

    def _register_batch_move_emails_tool(self, server: FastMCP, credential_store: CredentialStore) -> None:
        @server.tool(
            name="batch_move_emails",
            description=(
                "Move multiple messages to different destination folders in a single optimized batch operation. "
                "Each message can have a different destination. Provide config_id and message_operations as a list "
                "of {message_id, destination_folder} objects. The tool resolves folder names, manages location labels "
                "(INBOX, TRASH, etc.), and executes all moves in one API call. Returns detailed success/failure breakdown "
                "with per-message results including final label states. Supports up to 100 messages per call (automatically "
                "splits larger batches). Use this instead of calling move operations individually for better performance."
            ),
        )
        async def batch_move_emails(
            config_id: str,
            message_operations: Sequence[Mapping[str, Any]],
        ) -> dict[str, Any]:
            if not message_operations:
                msg = "At least one message operation is required."
                logger.error("Batch move failed - no operations | config_id=%s", config_id)
                raise ValueError(msg)

            config = credential_store.get_config(config_id)
            provider = getattr(config, "provider", None)
            client = self._require_client(provider)

            # Fetch folder list once for all operations (with caching for performance)
            folders = self._get_folders_cached(client, config, config_id)

            resolved_operations = []
            for op in message_operations:
                message_id = (op.get("message_id") or "").strip()
                destination_folder = (op.get("destination_folder") or "").strip()

                if not message_id:
                    msg = "Each operation must have a message_id."
                    raise ValueError(msg)
                if not destination_folder:
                    msg = "Each operation must have a destination_folder."
                    raise ValueError(msg)

                # Resolve destination folder to get folder info
                folder_info = self._resolve_destination_folder_from_list(folders, destination_folder)
                destination_label = folder_info.get("id") or folder_info.get("name")

                # Build add/remove label lists
                add_labels = [destination_label]
                remove_labels = self._get_location_labels_to_remove(provider, destination_label)

                resolved_operations.append({
                    "message_id": message_id,
                    "add_labels": add_labels,
                    "remove_labels": remove_labels,
                })

            batch_result = client.batch_move_messages(config, resolved_operations)

            success_count = batch_result.get("success_count", 0)
            failure_count = batch_result.get("failure_count", 0)

            return {
                "config_id": config_id,
                "provider": provider,
                "total_operations": len(message_operations),
                "success_count": success_count,
                "failure_count": failure_count,
                "success": batch_result.get("success", []),
                "failures": batch_result.get("failures", []),
            }

    def _register_mark_for_deletion_tool(self, server: FastMCP, credential_store: CredentialStore) -> None:
        @server.tool(
            name="mark_for_deletion",
            description=(
                "Ensure the provider-specific mark_for_deletion folder/label exists (creating it when supported) and "
                "move the supplied message_ids there for the given config_id using batch operations. Returns provider/folder "
                "metadata plus detailed success/failure breakdown with per-message results."
            ),
        )
        async def mark_for_deletion(
            config_id: str,
            message_ids: Sequence[str] | str,
        ) -> dict[str, Any]:
            message_id_list = self._normalize_message_ids(message_ids)
            config = credential_store.get_config(config_id)
            provider = getattr(config, "provider", None)
            client = self._require_client(provider)

            # Fetch folders once for efficiency (with caching for performance)
            folders = self._get_folders_cached(client, config, config_id)
            folder_info = self._ensure_mark_for_deletion_folder_from_list(client, config, folders)

            # Build batch operations for all messages
            destination_label = folder_info.get("id") or folder_info.get("name")
            remove_labels = self._get_location_labels_to_remove(provider, destination_label)

            message_operations = [
                {
                    "message_id": msg_id,
                    "add_labels": [destination_label],
                    "remove_labels": remove_labels,
                }
                for msg_id in message_id_list
            ]

            batch_result = client.batch_move_messages(config, message_operations)

            success_count = batch_result.get("success_count", 0)
            failure_count = batch_result.get("failure_count", 0)

            return {
                "config_id": config_id,
                "provider": provider,
                "folder": folder_info,
                "total_count": len(message_id_list),
                "success_count": success_count,
                "failure_count": failure_count,
                "success": batch_result.get("success", []),
                "failures": batch_result.get("failures", []),
            }

    def _register_read_email_resource_tool(self, server: FastMCP) -> None:
        @server.tool(
            name="read_email_resource",
            description=(
                "Return the JSON payload previously registered under a resource:// URI. "
                "Use this when a client cannot issue MCP resources/read directly."
            ),
        )
        async def read_email_resource(resource_uri: str) -> dict[str, Any]:
            resource_uri = (resource_uri or "").strip()
            if not resource_uri:
                msg = "resource_uri is required."
                raise ValueError(msg)
            payload = self._resource_cache.get(resource_uri)
            if payload is None:
                msg = f"resource_uri '{resource_uri}' is not available."
                raise ValueError(msg)
            return {
                "resource_uri": resource_uri,
                "payload": payload,
            }

    async def search_mailbox(
        self,
        server: FastMCP,
        credential_store: CredentialStore,
        config_id: str,
        *,
        query: str | None = None,
        subject: str | None = None,
        sender: str | None = None,
        recipient: str | None = None,
        folder: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        max_results: int | None = None,
    ) -> dict[str, Any]:
        config = credential_store.get_config(config_id)
        provider = getattr(config, "provider", None)
        client = self._require_client(provider)

        # Resolve max_results with default
        resolved_max_results = self._resolve_max_results(max_results)

        # Prepare and validate filters
        filters, normalized = self._prepare_filters(
            query=query,
            subject=subject,
            sender=sender,
            recipient=recipient,
            folder=folder,
            date_from=date_from,
            date_to=date_to,
        )

        result = client.search_messages(
            config,
            normalized,
            max_results=resolved_max_results,
        )

        messages = result.get("messages", [])
        total_count = result.get("total_count", len(messages))
        truncated = result.get("truncated", False)

        return {
            "config_id": config_id,
            "provider": provider or "unknown",
            "messages": messages,
            "total_count": total_count,
            "truncated": truncated,
            "filters_applied": normalized,
        }

    def _require_client(self, provider: str | None) -> Any:
        """Get email client for provider and raise if not available.

        Args:
            provider: Provider name (e.g., 'gmail')

        Returns:
            Email client instance

        Raises:
            ValueError: If no client configured for the provider
        """
        client = self._client_for_provider(provider)
        if not client:
            msg = f"Provider '{provider or 'unknown'}' is not configured for message tools."
            raise ValueError(msg)
        return client

    def _prepare_filters(
        self,
        *,
        query: str | None,
        subject: str | None,
        sender: str | None,
        recipient: str | None,
        folder: str | None,
        date_from: str | None,
        date_to: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Prepare and validate search filters for message queries.

        Normalizes filter values and validates that at least one filter criterion
        is provided. When no text-based filters are present, both date_from and
        date_to are required.

        Args:
            query: Freeform text search query
            subject: Subject line filter
            sender: Sender email address filter
            recipient: Recipient email address filter
            folder: Folder/label name filter
            date_from: ISO 8601 start date (normalized to start of day)
            date_to: ISO 8601 end date (normalized to end of day)

        Returns:
            Tuple of (original_filters, normalized_filters) where normalized_filters
            has ISO dates converted to UTC datetime strings

        Raises:
            ValueError: If no filters provided or missing required date filters
        """
        filters = {
            "query": (query or "").strip() or None,
            "subject": (subject or "").strip() or None,
            "sender": (sender or "").strip() or None,
            "recipient": (recipient or "").strip() or None,
            "folder": (folder or "").strip() or None,
            "date_from": (date_from or "").strip() or None,
            "date_to": (date_to or "").strip() or None,
        }
        if not any(value for key, value in filters.items() if key not in {"date_from", "date_to"}):
            if not (filters["date_from"] and filters["date_to"]):
                msg = (
                    "When no text/subject/sender/recipient/folder filters are provided, "
                    "both date_from and date_to must be supplied."
                )
                raise ValueError(msg)
        normalized = dict(filters)
        if filters["date_from"]:
            normalized["date_from"] = self._normalize_date(filters["date_from"], start_of_day=True)
        if filters["date_to"]:
            normalized["date_to"] = self._normalize_date(filters["date_to"], start_of_day=False)
        return filters, normalized

    def _normalize_date(self, value: str, *, start_of_day: bool) -> str:
        """Normalize ISO 8601 date string to start or end of day in UTC.

        Args:
            value: ISO 8601 date string
            start_of_day: If True, normalize to 00:00:00, else 23:59:59

        Returns:
            ISO 8601 datetime string in UTC timezone

        Raises:
            ValueError: If date string is invalid
        """
        try:
            parsed = parse_iso8601_to_datetime(value)
        except ValueError as exc:
            msg = f"Invalid ISO date '{value}'."
            raise ValueError(msg) from exc
        target_time = time(0, 0, 0) if start_of_day else time(23, 59, 59)
        normalized = datetime(
            parsed.year,
            parsed.month,
            parsed.day,
            target_time.hour,
            target_time.minute,
            target_time.second,
            tzinfo=parsed.tzinfo,
        )
        normalized = normalized.astimezone(timezone.utc)
        return normalized.isoformat()

    def _resolve_max_results(self, max_results: int | None) -> int:
        """Resolve max_results parameter with default and validation.

        Args:
            max_results: Optional limit on results

        Returns:
            Resolved max_results (default 500)

        Raises:
            ValueError: If max_results is out of range
        """
        if max_results is None:
            return 500  # Default limit
        if not 1 <= int(max_results) <= 1000:
            msg = "max_results must be between 1 and 1000."
            raise ValueError(msg)
        return int(max_results)

    def _normalize_addresses(self, values: Sequence[str] | str | None) -> list[str]:
        """Normalize email addresses to a list, stripping whitespace.

        Args:
            values: Single email address, sequence of addresses, or None

        Returns:
            List of non-empty email addresses with whitespace stripped
        """
        if values is None:
            return []
        if isinstance(values, str):
            items = [values]
        else:
            items = list(values)
        normalized = []
        for entry in items:
            entry = (entry or "").strip()
            if entry:
                normalized.append(entry)
        return normalized

    def _normalize_message_ids(self, message_ids: Sequence[str] | str) -> list[str]:
        """Normalize message IDs to a list, filtering empty values.

        Args:
            message_ids: Single message ID or sequence of message IDs

        Returns:
            List of non-empty message IDs with whitespace stripped

        Raises:
            ValueError: If no valid message IDs provided
        """
        if isinstance(message_ids, str):
            candidates = [message_ids]
        else:
            candidates = list(message_ids)
        normalized = []
        for value in candidates:
            trimmed = (value or "").strip()
            if not trimmed:
                continue
            normalized.append(trimmed)
        if not normalized:
            msg = "At least one message id is required."
            raise ValueError(msg)
        return normalized

    def _resolve_destination_folder_from_list(
        self,
        folders: list[dict[str, Any]],
        destination: str,
    ) -> dict[str, Any]:
        """Resolve destination folder from a pre-fetched folder list.

        Args:
            folders: List of folder dicts from list_folders()
            destination: Folder name or ID to resolve

        Returns:
            Folder dict with 'id' and 'name' keys

        Raises:
            ValueError: If folder not found
        """
        destination_lower = destination.lower()
        for folder in folders:
            folder_id = str(folder.get("id", ""))
            folder_name = str(folder.get("name", ""))
            if destination == folder_id or destination == folder_name:
                return dict(folder)
            if destination_lower in {folder_id.lower(), folder_name.lower()}:
                return dict(folder)
        msg = f"Folder '{destination}' does not exist for this provider."
        raise ValueError(msg)

    def _get_location_labels_to_remove(self, provider: str | None, destination_label: str) -> list[str]:
        """Determine which location labels to remove when moving to a destination.

        For Gmail, moving to a folder means removing other location labels like
        INBOX, TRASH, SPAM, and CATEGORY_* labels (unless moving to one of them).
        """
        if provider != "gmail":
            # For non-Gmail providers, no special location label handling needed
            return []

        # Gmail location labels that should be removed when moving
        # (except the destination itself)
        location_labels = [
            "INBOX",
            "TRASH",
            "SPAM",
            "CATEGORY_PERSONAL",
            "CATEGORY_SOCIAL",
            "CATEGORY_PROMOTIONS",
            "CATEGORY_UPDATES",
            "CATEGORY_FORUMS",
        ]

        # Remove all location labels except the destination
        destination_upper = destination_label.upper()
        return [label for label in location_labels if label != destination_upper]

    def _ensure_mark_for_deletion_folder_from_list(
        self,
        client: Any,
        config: EmailProviderConfig,
        folders: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Ensure mark_for_deletion folder exists using a pre-fetched folder list.

        Args:
            client: Email client instance
            config: Email provider configuration
            folders: Pre-fetched list of folders from list_folders()

        Returns:
            Folder dict with 'id' and 'name' keys

        Raises:
            ValueError: If folder doesn't exist and provider doesn't support creation
        """
        try:
            return self._resolve_destination_folder_from_list(folders, MARK_FOR_DELETION_NAME)
        except ValueError:
            if not client.supports_folder_creation:
                msg = (
                    "Provider does not support creating the mark_for_deletion folder automatically."
                )
                raise ValueError(msg)
            return client.create_folder(config, MARK_FOR_DELETION_NAME)

    def _register_resource(
        self,
        server: FastMCP,
        *,
        resource_uri: str,
        name: str,
        description: str,
        payload: Mapping[str, Any],
    ) -> None:
        serialized = json.dumps(payload, indent=2)
        self._resource_cache[resource_uri] = json.loads(serialized)

        def _reader() -> str:
            return serialized

        server.resource(
            resource_uri,
            name=name,
            description=description,
            mime_type="application/json",
        )(_reader)

    @staticmethod
    def _draft_resource_uri(draft_id: str) -> str:
        safe_id = quote(draft_id, safe="")
        return f"resource://messages/drafts/{safe_id}"


    @staticmethod
    def _full_resource_uri(message_id: str) -> str:
        safe_id = quote(message_id, safe="")
        return f"resource://messages/{safe_id}/full"






def register_message_tools(
    server: FastMCP,
    credential_store: CredentialStore,
    *,
    message_tools: MessageTools | None = None,
) -> None:
    """Attach message tools to the FastMCP server."""

    if message_tools is None:
        message_tools = MessageTools()

    message_tools.register(server, credential_store)

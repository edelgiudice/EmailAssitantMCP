"""Gmail client utilities for folders, drafts, and message operations."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from ..utils.datetime_utils import parse_iso8601_to_epoch
from ..utils.text_utils import strip_html, truncate_text
from email.message import EmailMessage
from email.utils import formataddr, parsedate_to_datetime
from typing import Any, Final, Mapping, Sequence
from urllib import error, parse, request

from cachetools import TTLCache
from ..config import EmailProviderConfig, GmailOAuthConfig
from ..logging_redaction import EMAIL_PATTERN, redact_token
from .base import EmailClient

GMAIL_DEFAULT_FOLDERS: Final[list[dict[str, str]]] = [
    {"id": "INBOX", "name": "Inbox", "type": "system"},
    {"id": "[Gmail]/Starred", "name": "Starred", "type": "system"},
    {"id": "[Gmail]/Sent Mail", "name": "Sent", "type": "system"},
    {"id": "[Gmail]/Drafts", "name": "Drafts", "type": "system"},
    {"id": "[Gmail]/Trash", "name": "Trash", "type": "system"},
]

LOGGER = logging.getLogger(__name__)
LABELS_ENDPOINT: Final = "https://gmail.googleapis.com/gmail/v1/users/me/labels"
USER_BASE_ENDPOINT: Final = "https://gmail.googleapis.com/gmail/v1/users/me"
MESSAGES_ENDPOINT: Final = f"{USER_BASE_ENDPOINT}/messages"
DRAFTS_ENDPOINT: Final = f"{USER_BASE_ENDPOINT}/drafts"
BATCH_MODIFY_ENDPOINT: Final = f"{USER_BASE_ENDPOINT}/messages/batchModify"
PREVIEW_LIMIT = 2000
FULL_BODY_LIMIT = 10000
SNIPPET_LIMIT = 200
FLAG_LABELS = {"UNREAD", "STARRED", "IMPORTANT"}
# System labels that don't require name-to-ID resolution
SYSTEM_LABELS: Final[set[str]] = {
    "INBOX",
    "SENT",
    "DRAFT",
    "TRASH",
    "SPAM",
    "UNREAD",
    "STARRED",
    "IMPORTANT",
    "CATEGORY_PERSONAL",
    "CATEGORY_SOCIAL",
    "CATEGORY_PROMOTIONS",
    "CATEGORY_UPDATES",
    "CATEGORY_FORUMS",
}
# Gmail "folders" that should be cleared when applying a new destination label.
LOCATION_LABELS: Final[tuple[str, ...]] = (
    "INBOX",
    "TRASH",
    "SPAM",
    "CATEGORY_PERSONAL",
    "CATEGORY_FORUMS",
    "CATEGORY_PROMOTIONS",
    "CATEGORY_SOCIAL",
    "CATEGORY_UPDATES",
)


class GmailClient(EmailClient):
    """Fetch Gmail folders and coordinate message-level operations."""

    provider: Final[str] = "gmail"

    def __init__(
        self,
        labels_endpoint: str = LABELS_ENDPOINT,
        user_base_endpoint: str = USER_BASE_ENDPOINT,
    ) -> None:
        self._labels_endpoint = labels_endpoint
        self._user_base_endpoint = user_base_endpoint.rstrip("/")
        self._messages_endpoint = f"{self._user_base_endpoint}/messages"
        self._drafts_endpoint = f"{self._user_base_endpoint}/drafts"
        self._batch_modify_endpoint = f"{self._user_base_endpoint}/messages/batchModify"
        # Label caching for batch operations (name -> ID mapping, 5 min TTL)
        self._label_cache: TTLCache[str, str] = TTLCache(maxsize=1000, ttl=300)
        # Access token caching (stores token with expiry time, 1 hour default)
        self._access_token_cache: TTLCache[str, tuple[str, datetime]] = TTLCache(maxsize=10, ttl=3600)

    @property
    def supports_folder_creation(self) -> bool:
        return True

    def list_folders(self, config: EmailProviderConfig) -> list[dict[str, str]]:
        """Return every available Gmail label as a folder entry."""
        LOGGER.debug("Listing Gmail folders")
        gmail_config = self._require_config(config)
        access_token = self._refresh_access_token(gmail_config)
        labels = self._fetch_labels(access_token)

        # Populate label cache while building folders list
        for label in labels:
            name = label.get("name")
            label_id = label.get("id")
            if name and label_id:
                self._label_cache[name] = label_id

        folders: list[dict[str, str]] = []
        for label in labels:
            label_id = label.get("id")
            name = label.get("name")
            if not label_id or not name:
                continue
            # Build folder entry
            label_type = label.get("type", "user")
            folders.append(
                {
                    "id": label_id,
                    "name": name,
                    "type": "system" if label_type == "system" else "user",
                }
            )
        LOGGER.info("Gmail folders retrieved | folder_count=%d", len(folders))
        return folders

    def create_folder(
        self,
        config: EmailProviderConfig,
        folder_name: str,
        parent_folder: str | None = None,
    ) -> dict[str, str]:
        """Create a Gmail label to mirror the requested folder structure."""
        LOGGER.info("Creating Gmail folder | folder_name=%s parent=%s", folder_name, parent_folder or "none")
        gmail_config = self._require_config(config)
        folder_name = folder_name.strip()
        if not folder_name:
            msg = "A folder name is required for Gmail folder creation."
            LOGGER.error("Folder creation failed - empty name")
            raise ValueError(msg)
        parent_folder = (parent_folder or "").strip()
        label_name = folder_name if not parent_folder else f"{parent_folder}/{folder_name}"
        access_token = self._refresh_access_token(gmail_config)
        label = self._create_label(access_token, label_name)
        label_id = label.get("id")
        label_display_name = label.get("name")
        if not label_id or not label_display_name:
            msg = "Google returned an invalid label payload during folder creation."
            LOGGER.error("Invalid label payload received from Google")
            raise RuntimeError(msg)
        label_type = label.get("type", "user")
        LOGGER.info("Gmail folder created | label_id=%s label_name=%s", label_id, label_display_name)
        return {
            "id": label_id,
            "name": label_display_name,
            "type": "system" if label_type == "system" else "user",
        }

    def create_draft(self, config: EmailProviderConfig, payload: Mapping[str, Any]) -> dict[str, Any]:
        to = payload.get("to", "")
        subject = payload.get("subject", "")
        LOGGER.info("Creating Gmail draft | to=%s subject=%s", to, subject[:50] if subject else "")
        gmail_config = self._require_config(config)
        access_token = self._refresh_access_token(gmail_config)
        mime_message = self._compose_draft_message(gmail_config, payload)
        encoded = base64.urlsafe_b64encode(mime_message.as_bytes()).decode("utf-8")
        draft_payload: dict[str, Any] = {"message": {"raw": encoded}}
        thread_id = (payload.get("thread_id") or "").strip()
        if thread_id:
            draft_payload["message"]["threadId"] = thread_id
        response = self._gmail_request(
            access_token,
            "POST",
            self._drafts_endpoint,
            payload=draft_payload,
        )
        message = response.get("message", {})
        draft_id = response.get("id")
        message_id = message.get("id")
        LOGGER.info("Gmail draft created | draft_id=%s message_id=%s", draft_id, message_id)
        return {
            "draft_id": draft_id,
            "message_id": message_id,
            "thread_id": message.get("threadId"),
            "raw": response,
        }

    def search_messages(
        self,
        config: EmailProviderConfig,
        filters: Mapping[str, Any],
        *,
        max_results: int | None = None,
    ) -> dict[str, Any]:
        LOGGER.debug("Searching Gmail messages | max_results=%s", max_results or "default(500)")
        gmail_config = self._require_config(config)
        access_token = self._refresh_access_token(gmail_config)
        query = self._build_search_query(filters)
        LOGGER.debug("Gmail search query | query=%s", query or "none")

        # Resolve max_results with default of 500
        max_results_resolved = max_results if max_results is not None else 500

        all_messages: list[dict[str, Any]] = []
        page_token: str | None = None

        # Fetch all pages until we hit max_results or run out of results
        while True:
            # Calculate how many more messages we can fetch
            remaining = max_results_resolved - len(all_messages)
            if remaining <= 0:
                break

            # Request a page (max 100 per request for efficiency)
            params: dict[str, Any] = {"maxResults": min(100, remaining)}
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token

            response = self._gmail_request(access_token, "GET", self._messages_endpoint, params=params)
            entries = response.get("messages", []) or []
            LOGGER.debug("Gmail search page returned | entry_count=%d", len(entries))

            # Fetch full details for each message in this page
            for entry in entries:
                message_id = entry.get("id")
                if not message_id:
                    continue
                detail = self._gmail_request(
                    access_token,
                    "GET",
                    f"{self._messages_endpoint}/{message_id}",
                    params={"format": "full"},
                )
                all_messages.append(self._normalize_message_payload(detail, include_full_body=False))

                # Stop if we've reached max_results
                if len(all_messages) >= max_results_resolved:
                    break

            # Check if there are more pages
            page_token = response.get("nextPageToken")
            if not page_token or len(all_messages) >= max_results_resolved:
                break

        truncated = len(all_messages) >= max_results_resolved

        LOGGER.info(
            "Gmail search completed | message_count=%d truncated=%s",
            len(all_messages),
            truncated
        )

        return {
            "messages": all_messages,
            "total_count": len(all_messages),
            "truncated": truncated,
        }

    def fetch_message_full(self, config: EmailProviderConfig, message_id: str) -> dict[str, Any]:
        LOGGER.debug("Fetching full Gmail message | message_id=%s", message_id)
        gmail_config = self._require_config(config)
        access_token = self._refresh_access_token(gmail_config)
        message_id = message_id.strip()
        if not message_id:
            msg = "message_id is required for Gmail fetch operations."
            LOGGER.error("Fetch message failed - empty message_id")
            raise ValueError(msg)
        payload = self._gmail_request(
            access_token,
            "GET",
            f"{self._messages_endpoint}/{message_id}",
            params={"format": "full"},
        )
        LOGGER.info("Gmail message fetched | message_id=%s", message_id)
        return self._normalize_message_payload(payload, include_full_body=True)

    def _refresh_access_token(self, config: GmailOAuthConfig) -> str:
        # Check if we have a valid cached token with 60s buffer
        cache_key = "token"
        cached_entry = self._access_token_cache.get(cache_key)
        if cached_entry:
            cached_token, expiry_time = cached_entry
            now = datetime.now(timezone.utc)
            # Apply 60s buffer - only use token if it has > 60s remaining
            if now + timedelta(seconds=60) < expiry_time:
                remaining_seconds = (expiry_time - now).total_seconds()
                LOGGER.debug(
                    "Using cached access token | remaining_seconds=%.0f",
                    remaining_seconds
                )
                return cached_token

        LOGGER.debug("Refreshing Gmail access token")
        start_time = time.perf_counter()

        payload = parse.urlencode(
            {
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "refresh_token": config.refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        req = request.Request(
            config.token_uri,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=15) as resp:
                response_payload = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:  # pragma: no cover - network failures
            duration_ms = (time.perf_counter() - start_time) * 1000
            detail = exc.read().decode("utf-8", errors="ignore")
            # Redact email addresses from error details for security
            redacted_detail = EMAIL_PATTERN.sub(lambda m: f"***@{m.group(1)}", detail)
            LOGGER.error(
                "Gmail token refresh failed | status=%s duration_ms=%.2f error=%s",
                exc.code,
                duration_ms,
                redacted_detail
            )
            raise
        except error.URLError as exc:  # pragma: no cover - network failures
            duration_ms = (time.perf_counter() - start_time) * 1000
            LOGGER.error(
                "Gmail token refresh network error | duration_ms=%.2f error=%s",
                duration_ms,
                str(exc.reason)
            )
            raise
        access_token = response_payload.get("access_token")
        if not access_token:
            msg = "Google returned an empty access token during folder discovery."
            LOGGER.error("Empty access token received from Google")
            raise RuntimeError(msg)

        duration_ms = (time.perf_counter() - start_time) * 1000
        expires_in = response_payload.get("expires_in", 3599)

        # Cache the token with expiry time
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self._access_token_cache[cache_key] = (access_token, expiry_time)

        LOGGER.info(
            "Gmail access token refreshed | duration_ms=%.2f expires_in=%s",
            duration_ms,
            expires_in
        )
        LOGGER.debug(
            "Access token details | token=%s",
            redact_token(access_token)
        )
        return access_token

    def _fetch_labels(self, access_token: str) -> list[dict[str, str]]:
        LOGGER.debug("Fetching Gmail labels")
        start_time = time.perf_counter()
        req = request.Request(
            self._labels_endpoint,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:  # pragma: no cover - network failures
            duration_ms = (time.perf_counter() - start_time) * 1000
            detail = exc.read().decode("utf-8", errors="ignore")
            # Redact email addresses from error details for security
            redacted_detail = EMAIL_PATTERN.sub(lambda m: f"***@{m.group(1)}", detail)
            LOGGER.error(
                "Gmail label fetch failed | status=%s duration_ms=%.2f error=%s",
                exc.code,
                duration_ms,
                redacted_detail
            )
            raise
        except error.URLError as exc:  # pragma: no cover - network failures
            duration_ms = (time.perf_counter() - start_time) * 1000
            LOGGER.error(
                "Gmail label fetch network error | duration_ms=%.2f error=%s",
                duration_ms,
                str(exc.reason)
            )
            raise
        labels = payload.get("labels", [])
        label_list = [dict(label) for label in labels if isinstance(label, dict)]
        duration_ms = (time.perf_counter() - start_time) * 1000
        LOGGER.debug("Gmail labels fetched | label_count=%d duration_ms=%.2f", len(label_list), duration_ms)
        return label_list

    def _create_label(self, access_token: str, label_name: str) -> dict[str, str]:
        LOGGER.debug("Creating Gmail label | label_name=%s", label_name)
        payload = json.dumps(
            {
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }
        ).encode("utf-8")
        req = request.Request(
            self._labels_endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=15) as resp:
                response_payload = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:  # pragma: no cover - network failures
            detail = exc.read().decode("utf-8", errors="ignore")
            # Redact email addresses from error details for security
            redacted_detail = EMAIL_PATTERN.sub(lambda m: f"***@{m.group(1)}", detail)
            LOGGER.error(
                "Gmail label creation failed | status=%s label_name=%s error=%s",
                exc.code,
                label_name,
                redacted_detail
            )
            raise
        except error.URLError as exc:  # pragma: no cover - network failures
            LOGGER.error(
                "Gmail label creation network error | label_name=%s error=%s",
                label_name,
                str(exc.reason)
            )
            raise
        label_id = response_payload.get("id")
        LOGGER.info("Gmail label created | label_id=%s label_name=%s", label_id, label_name)
        return response_payload

    def _gmail_request(
        self,
        access_token: str,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        start_time = time.perf_counter()
        query_url = url
        if params:
            filtered = {key: value for key, value in params.items() if value not in (None, "")}
            if filtered:
                query_url = f"{url}?{parse.urlencode(filtered, doseq=True)}"
        data = None
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(query_url, data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:  # pragma: no cover - network failures
            duration_ms = (time.perf_counter() - start_time) * 1000
            detail = exc.read().decode("utf-8", errors="ignore")
            # Redact email addresses from error details for security
            redacted_detail = EMAIL_PATTERN.sub(lambda m: f"***@{m.group(1)}", detail)
            LOGGER.error(
                "Gmail request failed | method=%s url=%s status=%s duration_ms=%.2f error=%s",
                method,
                url,
                exc.code,
                duration_ms,
                redacted_detail
            )
            raise
        except error.URLError as exc:  # pragma: no cover - network failures
            duration_ms = (time.perf_counter() - start_time) * 1000
            LOGGER.error(
                "Gmail request network error | method=%s url=%s duration_ms=%.2f error=%s",
                method,
                url,
                duration_ms,
                str(exc.reason)
            )
            raise
        duration_ms = (time.perf_counter() - start_time) * 1000
        LOGGER.debug("Gmail request completed | method=%s url=%s duration_ms=%.2f", method, url, duration_ms)
        return json.loads(raw) if raw else {}

    def _compose_draft_message(
        self,
        config: GmailOAuthConfig,
        payload: Mapping[str, Any],
    ) -> EmailMessage:
        message = EmailMessage()
        sender = config.email_address
        if getattr(config, "display_name", None):
            sender = formataddr((config.display_name, config.email_address))
        message["From"] = sender
        for header in ("to", "cc", "bcc"):
            recipients = payload.get(header)
            if recipients:
                message[header.title()] = ", ".join(recipients)
        subject = payload.get("subject")
        if subject:
            message["Subject"] = subject
        in_reply_to = payload.get("in_reply_to")
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
            message["References"] = in_reply_to
        body_text = payload.get("body_text")
        body_html = payload.get("body_html")
        if body_text:
            message.set_content(body_text)
            if body_html:
                message.add_alternative(body_html, subtype="html")
        elif body_html:
            message.set_content("This message contains HTML content.")
            message.add_alternative(body_html, subtype="html")
        else:  # fallback safety
            message.set_content("")
        return message

    def _build_search_query(self, filters: Mapping[str, Any]) -> str:
        terms: list[str] = []
        query = (filters.get("query") or "").strip()
        if query:
            terms.append(query)
        subject = (filters.get("subject") or "").strip()
        if subject:
            terms.append(f"subject:{self._quote_term(subject)}")
        sender = (filters.get("sender") or "").strip()
        if sender:
            terms.append(f"from:{self._quote_term(sender)}")
        recipient = (filters.get("recipient") or "").strip()
        if recipient:
            quoted = self._quote_term(recipient)
            terms.append(f"(to:{quoted} OR cc:{quoted})")
        folder = (filters.get("folder") or "").strip()
        if folder:
            terms.append(f"label:{self._quote_term(folder)}")
        date_from = (filters.get("date_from") or "").strip()
        if date_from:
            terms.append(f"after:{parse_iso8601_to_epoch(date_from)}")
        date_to = (filters.get("date_to") or "").strip()
        if date_to:
            terms.append(f"before:{parse_iso8601_to_epoch(date_to)}")
        return " ".join(terms)

    @staticmethod
    def _quote_term(value: str) -> str:
        if not value:
            return ""
        safe = value.replace('"', "'").strip()
        if any(char.isspace() for char in safe):
            return f'"{safe}"'
        return safe

    def _normalize_message_payload(
        self,
        payload: Mapping[str, Any],
        *,
        include_full_body: bool,
    ) -> dict[str, Any]:
        headers = self._headers_to_map(payload.get("payload"))
        text_body, html_body, attachments = self._collect_bodies(payload.get("payload"))
        preview_source = text_body or strip_html(html_body) or payload.get("snippet", "")
        body_preview, preview_truncated = truncate_text(preview_source or "", PREVIEW_LIMIT)
        snippet_value, _ = truncate_text(payload.get("snippet", ""), SNIPPET_LIMIT)
        sent_at = self._parse_header_date(headers.get("date"))
        received_at = self._ms_to_iso(payload.get("internalDate"))
        label_ids = payload.get("labelIds", []) or []
        envelope: dict[str, Any] = {
            "id": payload.get("id"),
            "thread_id": payload.get("threadId"),
            "subject": headers.get("subject"),
            "from": headers.get("from"),
            "to": self._split_addresses(headers.get("to")),
            "cc": self._split_addresses(headers.get("cc")),
            "bcc": self._split_addresses(headers.get("bcc")),
            "snippet": snippet_value,
            "sent_at": sent_at,
            "received_at": received_at,
            "labels": list(label_ids),
            "flags": self._flags_from_labels(label_ids),
            "has_attachments": bool(attachments),
            "body_preview": body_preview,
            "body_preview_truncated": preview_truncated,
        }
        if include_full_body:
            text_value, text_truncated = truncate_text(text_body or "", FULL_BODY_LIMIT)
            html_value, html_truncated = truncate_text(html_body or "", FULL_BODY_LIMIT)
            envelope["text_body"] = text_value or None
            envelope["html_body"] = html_value or None
            envelope["body_truncated"] = text_truncated or html_truncated
            envelope["attachments"] = attachments
        return envelope

    @staticmethod
    def _headers_to_map(payload_node: Mapping[str, Any] | None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if not payload_node:
            return headers
        for raw in payload_node.get("headers", []) or []:
            name = raw.get("name")
            value = raw.get("value")
            if not name or value is None:
                continue
            headers[name.lower()] = value
        return headers

    @staticmethod
    def _split_addresses(value: str | None) -> list[str]:
        if not value:
            return []
        return [part.strip() for part in value.split(",") if part.strip()]

    def _collect_bodies(
        self,
        payload_node: Mapping[str, Any] | None,
    ) -> tuple[str | None, str | None, list[dict[str, Any]]]:
        text_parts: list[str] = []
        html_parts: list[str] = []
        attachments: list[dict[str, Any]] = []

        def _walk(node: Mapping[str, Any] | None) -> None:
            if not node:
                return
            mime_type = node.get("mimeType", "")
            body = node.get("body") or {}
            data = body.get("data")
            decoded = self._decode_part_data(data) if data else ""
            if mime_type == "text/plain" and decoded:
                text_parts.append(decoded)
            elif mime_type == "text/html" and decoded:
                html_parts.append(decoded)
            attachment_id = body.get("attachmentId")
            filename = node.get("filename")
            if attachment_id or (filename and mime_type and not mime_type.startswith("text/")):
                attachments.append(
                    {
                        "filename": filename,
                        "mime_type": mime_type,
                        "attachment_id": attachment_id,
                        "size": body.get("size"),
                    }
                )
            for child in node.get("parts") or []:
                _walk(child)

        _walk(payload_node or {})
        text_value = "\n".join(text_parts).strip() or None
        html_value = "\n".join(html_parts).strip() or None
        filtered_attachments = [att for att in attachments if att.get("filename") or att.get("attachment_id")]
        return text_value, html_value, filtered_attachments

    @staticmethod
    def _decode_part_data(data: str) -> str:
        if not data:
            return ""
        padding = "=" * (-len(data) % 4)
        try:
            decoded = base64.urlsafe_b64decode(f"{data}{padding}".encode("utf-8"))
        except (ValueError, binascii.Error):  # pragma: no cover - defensive
            return ""
        return decoded.decode("utf-8", errors="ignore")



    @staticmethod
    def _ms_to_iso(value: str | int | None) -> str | None:
        if value is None:
            return None
        try:
            millis = int(value)
        except (TypeError, ValueError):
            return None
        seconds = millis / 1000
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()

    @staticmethod
    def _parse_header_date(value: str | None) -> str | None:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _flags_from_labels(label_ids: Sequence[str]) -> list[str]:
        flags = []
        for label in label_ids:
            if label in FLAG_LABELS:
                flags.append(label)
        return flags

    def _labels_to_remove_for_move(self, destination_id: str) -> list[str]:
        normalized = (destination_id or "").strip().upper()
        removals = [label for label in LOCATION_LABELS if label != normalized]
        return removals

    def _refresh_label_cache(self, access_token: str) -> None:
        """Fetch all labels and update cache."""
        labels = self._fetch_labels(access_token)
        for label in labels:
            name = label.get("name")
            label_id = label.get("id")
            if name and label_id:
                self._label_cache[name] = label_id

    def _resolve_label_names(
        self,
        access_token: str,
        label_names: list[str]
    ) -> list[str]:
        """Convert label names to label IDs with caching.

        Args:
            access_token: Valid OAuth token
            label_names: List of label names or IDs (e.g., ["Tennis", "INBOX", "Label_123"])

        Returns:
            List of label IDs (e.g., ["Label_123", "INBOX", "Label_123"])

        Raises:
            ValueError: If a label name is not found after cache refresh

        Note:
            If a label ID is passed in (starts with "Label_"), it's returned unchanged.
        """
        if not label_names:
            return []

        cache_refreshed = False
        resolved = []
        cache_hits = 0
        cache_misses = 0

        for name in label_names:
            # System labels pass through unchanged
            if name.upper() in SYSTEM_LABELS:
                resolved.append(name.upper())
            # Label IDs (Label_*) pass through unchanged
            elif name.startswith("Label_"):
                resolved.append(name)
            else:
                # Look up in cache
                label_id = self._label_cache.get(name)
                if label_id:
                    resolved.append(label_id)
                    cache_hits += 1
                else:
                    cache_misses += 1
                    # Refresh cache and try again
                    if not cache_refreshed:
                        LOGGER.debug("Label not found in cache, refreshing | label=%s", name)
                        self._refresh_label_cache(access_token)
                        cache_refreshed = True
                    label_id = self._label_cache.get(name)
                    if label_id:
                        resolved.append(label_id)
                    else:
                        LOGGER.error("Label not found after cache refresh | label=%s", name)
                        raise ValueError(f"Label '{name}' not found")

        if cache_hits > 0 or cache_misses > 0:
            LOGGER.debug(
                "Label resolution completed | requested=%d resolved=%d cache_hits=%d cache_misses=%d",
                len(label_names),
                len(resolved),
                cache_hits,
                cache_misses
            )

        return resolved


    @staticmethod
    def default_folders() -> list[dict[str, str]]:
        return [dict(entry) for entry in GMAIL_DEFAULT_FOLDERS]

    def batch_move_messages(
        self,
        config: EmailProviderConfig,
        message_operations: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Move multiple messages with different label configurations using batch HTTP.

        Args:
            config: Gmail OAuth configuration
            message_operations: List of operations, each containing:
                - message_id: str
                - add_labels: List[str] (label names or IDs)
                - remove_labels: List[str] (label names or IDs)

        Returns:
            Dict with success/failure breakdown per message
        """
        LOGGER.info("Starting Gmail batch move | operation_count=%d", len(message_operations))
        start_time = time.perf_counter()

        gmail_config = self._require_config(config)
        access_token = self._refresh_access_token(gmail_config)

        # Resolve label names to IDs
        LOGGER.debug("Resolving label names for batch operations")
        resolved_ops = []
        for op in message_operations:
            add_labels = op.get("add_labels", [])
            remove_labels = op.get("remove_labels", [])

            add_label_ids = self._resolve_label_names(access_token, add_labels)
            remove_label_ids = self._resolve_label_names(access_token, remove_labels)

            resolved_ops.append({
                "message_id": op["message_id"],
                "addLabelIds": add_label_ids,
                "removeLabelIds": remove_label_ids
            })

        # Split into batches of 100 (Gmail API limit)
        batch_count = (len(resolved_ops) + 99) // 100
        LOGGER.debug("Splitting into batches | batch_count=%d batch_size=100", batch_count)
        all_results = {"success": [], "failures": []}
        for i in range(0, len(resolved_ops), 100):
            batch = resolved_ops[i:i+100]
            batch_num = (i // 100) + 1
            LOGGER.debug("Executing batch | batch_num=%d/%d operation_count=%d", batch_num, batch_count, len(batch))
            result = self._execute_batch(access_token, batch)
            all_results["success"].extend(result["success"])
            all_results["failures"].extend(result["failures"])

        all_results["total_count"] = len(message_operations)
        all_results["success_count"] = len(all_results["success"])
        all_results["failure_count"] = len(all_results["failures"])

        duration_ms = (time.perf_counter() - start_time) * 1000
        LOGGER.info(
            "Gmail batch move completed | total=%d success=%d failures=%d duration_ms=%.2f",
            all_results["total_count"],
            all_results["success_count"],
            all_results["failure_count"],
            duration_ms
        )

        return all_results

    def _execute_batch(
        self,
        access_token: str,
        updates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute single batch request (up to 100 operations)."""
        LOGGER.debug("Executing Gmail batch HTTP request | operation_count=%d", len(updates))
        start_time = time.perf_counter()

        boundary = f"batch_boundary_{uuid.uuid4().hex}"
        body = self._build_batch_request_body(updates, boundary)

        req = request.Request(
            "https://gmail.googleapis.com/batch/gmail/v1",
            data=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": f"multipart/mixed; boundary={boundary}"
            },
            method="POST"
        )

        try:
            with request.urlopen(req, timeout=60) as resp:
                response_content = resp.read().decode("utf-8")
                content_type = resp.headers.get("Content-Type", "")
                status_code = resp.status
        except error.HTTPError as exc:  # pragma: no cover - network failures
            duration_ms = (time.perf_counter() - start_time) * 1000
            detail = exc.read().decode("utf-8", errors="ignore")
            # Redact email addresses from error details for security
            redacted_detail = EMAIL_PATTERN.sub(lambda m: f"***@{m.group(1)}", detail)
            LOGGER.error(
                "Gmail batch HTTP request failed | status=%s duration_ms=%.2f error=%s",
                exc.code,
                duration_ms,
                redacted_detail
            )
            raise
        except error.URLError as exc:  # pragma: no cover - network failures
            duration_ms = (time.perf_counter() - start_time) * 1000
            LOGGER.error(
                "Gmail batch HTTP request network error | duration_ms=%.2f error=%s",
                duration_ms,
                str(exc.reason)
            )
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000
        LOGGER.debug("Gmail batch HTTP response received | status=%d duration_ms=%.2f", status_code, duration_ms)

        return self._parse_batch_response(response_content, content_type, updates)

    def _build_batch_request_body(
        self,
        message_updates: list[dict[str, Any]],
        boundary: str,
    ) -> bytes:
        """Build multipart batch request body.

        Args:
            message_updates: List of dicts with structure:
                {
                    "message_id": str,
                    "addLabelIds": List[str],  # Already resolved to label IDs
                    "removeLabelIds": List[str]
                }
            boundary: Unique boundary string for this request

        Returns:
            Complete request body as bytes
        """
        parts = []

        for i, update in enumerate(message_updates):
            content_id = f"item{i}"
            message_id = update["message_id"]

            # Build modify request JSON
            modify_request = {}
            if update.get("addLabelIds"):
                modify_request["addLabelIds"] = update["addLabelIds"]
            if update.get("removeLabelIds"):
                modify_request["removeLabelIds"] = update["removeLabelIds"]

            request_body = json.dumps(modify_request)

            # Build multipart section
            part = f"--{boundary}\r\n"
            part += "Content-Type: application/http\r\n"
            part += f"Content-ID: <{content_id}>\r\n"
            part += "\r\n"
            part += f"POST /gmail/v1/users/me/messages/{message_id}/modify\r\n"
            part += "Content-Type: application/json\r\n"
            part += "\r\n"
            part += f"{request_body}\r\n"

            parts.append(part)

        # Combine all parts and add final boundary
        body = "".join(parts)
        body += f"--{boundary}--"

        return body.encode("utf-8")

    def _parse_batch_response(
        self,
        response_content: str,
        content_type: str,
        message_updates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Parse multipart batch response using email.parser.

        Args:
            response_content: Raw response body text
            content_type: Content-Type header value
            message_updates: Original operations (for mapping)

        Returns:
            {
                "success": [{"message_id": ..., "final_labels": [...], "thread_id": ...}],
                "failures": [{"message_id": ..., "error_code": ..., "error_message": ...}]
            }
        """
        from email import message_from_string

        LOGGER.debug("Parsing Gmail batch response | expected_count=%d", len(message_updates))

        # Parse multipart MIME message using standard library
        msg = message_from_string(f"Content-Type: {content_type}\r\n\r\n{response_content}")

        if not msg.is_multipart():
            LOGGER.error("Batch response is not multipart")
            raise ValueError("Expected multipart batch response")

        parts = msg.get_payload()
        success = []
        failures = []

        for idx, part in enumerate(parts):
            if idx >= len(message_updates):
                LOGGER.warning("Response index %d exceeds message_updates length %d", idx, len(message_updates))
                break

            message_id = message_updates[idx]["message_id"]

            # Each part contains an HTTP response
            http_response = part.get_payload()

            # Extract status code from HTTP status line
            status_match = re.search(r'HTTP/1\.\d+\s+(\d+)', http_response)
            if not status_match:
                LOGGER.debug("No status code found in part at index %d", idx)
                continue

            status_code = int(status_match.group(1))

            # Extract JSON body after HTTP headers (after blank line)
            json_match = re.search(r'(?:\r?\n){2,}(.+)', http_response, re.DOTALL)
            if not json_match:
                LOGGER.debug("No JSON body found in part at index %d with status %d", idx, status_code)
                continue

            json_body = json_match.group(1).strip()

            # Parse JSON response
            try:
                parsed_body = json.loads(json_body)
            except json.JSONDecodeError as e:
                LOGGER.warning(
                    "Malformed JSON in batch response | message_id=%s status=%d json_error=%s",
                    message_id, status_code, str(e)
                )
                failures.append({
                    "message_id": message_id,
                    "error_code": status_code,
                    "error_message": "Malformed response JSON",
                    "error_status": "PARSE_ERROR"
                })
                continue

            # Categorize success vs failure by HTTP status
            if 200 <= status_code < 300:
                success.append({
                    "message_id": parsed_body.get("id"),
                    "thread_id": parsed_body.get("threadId"),
                    "final_labels": parsed_body.get("labelIds", []),
                })
            else:
                error_info = parsed_body.get("error", {})
                error_message = error_info.get("message", "Unknown error")
                LOGGER.warning("Batch operation failed | message_id=%s status=%d error=%s",
                              message_id, status_code, error_message)
                failures.append({
                    "message_id": message_id,
                    "error_code": error_info.get("code", status_code),
                    "error_message": error_message,
                    "error_status": error_info.get("status", "UNKNOWN")
                })

        LOGGER.debug("Batch response parsed | success_count=%d failure_count=%d", len(success), len(failures))
        return {"success": success, "failures": failures}

    @staticmethod
    def _require_config(config: EmailProviderConfig) -> GmailOAuthConfig:
        if not isinstance(config, GmailOAuthConfig):
            msg = "Gmail configuration required for Gmail folder operations."
            raise TypeError(msg)
        return config

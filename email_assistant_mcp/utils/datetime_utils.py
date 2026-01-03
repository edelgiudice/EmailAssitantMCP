"""Shared date/time parsing and manipulation utilities.

This module consolidates date/time parsing logic that was previously
duplicated across multiple files in the codebase:
- ISO 8601 date string parsing with timezone handling
- Unix epoch timestamp conversion
- Current UTC timestamp generation

All functions return timezone-aware datetime objects to prevent
timezone-related bugs.
"""

from __future__ import annotations

from datetime import datetime, timezone


def parse_iso8601_to_datetime(date_str: str, *, normalize_to_utc: bool = False) -> datetime:
    """Parse ISO 8601 date string to datetime object.

    Handles common ISO 8601 formats including:
    - Strings ending with 'Z' (converted to '+00:00')
    - Strings with explicit timezone offsets
    - Naive strings (assumed to be UTC)

    Args:
        date_str: ISO 8601 formatted date string
        normalize_to_utc: If True, convert result to UTC timezone

    Returns:
        Parsed datetime object with timezone info

    Raises:
        ValueError: If date_str is not valid ISO 8601 format
    """
    text = date_str.strip()

    # Validate strict ISO 8601: must use 'T' as separator, not space
    # Check if this looks like a datetime (has both date and time parts)
    # and ensure it uses 'T' separator
    if " " in text and any(c in text for c in [":", "-"]):
        # Has a space and looks like a datetime string
        msg = f"Invalid ISO 8601 date string: '{date_str}' (use 'T' separator, not space)"
        raise ValueError(msg)

    # Convert 'Z' suffix to explicit UTC offset
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    # Parse the ISO format string
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        msg = f"Invalid ISO 8601 date string: '{date_str}'"
        raise ValueError(msg) from exc

    # Add UTC timezone if missing
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    # Optionally normalize to UTC
    if normalize_to_utc and parsed.tzinfo is not timezone.utc:
        parsed = parsed.astimezone(timezone.utc)

    return parsed


def parse_iso8601_to_epoch(date_str: str) -> int:
    """Parse ISO 8601 date string to Unix epoch timestamp (seconds).

    Args:
        date_str: ISO 8601 formatted date string

    Returns:
        Unix timestamp in seconds

    Raises:
        ValueError: If date_str is not valid ISO 8601 format
    """
    parsed = parse_iso8601_to_datetime(date_str)
    return int(parsed.timestamp())


def utc_now() -> datetime:
    """Get current UTC time as a timezone-aware datetime object.

    Returns:
        Current time in UTC timezone
    """
    return datetime.now(timezone.utc)

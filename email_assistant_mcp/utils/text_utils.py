"""Shared text manipulation utilities."""

from __future__ import annotations

import re

# Pre-compiled regex pattern for HTML tag removal
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def truncate_text(value: str | None, limit: int, *, strip: bool = False) -> tuple[str, bool]:
    """Truncate text to a maximum length, optionally adding ellipsis.

    Args:
        value: Text to truncate (None is treated as empty string)
        limit: Maximum length of the output text
        strip: If True, strip whitespace before truncating

    Raises:
        ValueError: If limit is negative

    Returns:
        Tuple of (truncated_text, was_truncated)
        - truncated_text: The text, truncated if necessary with "..." suffix
        - was_truncated: True if text was shortened, False otherwise

    Examples:
        truncate_text("Hello world", 20)
        # Returns: ('Hello world', False)

        truncate_text("Hello world", 8)
        # Returns: ('Hello...', True)

        truncate_text("Hello world", 2)
        # Returns: ('He', True)

        truncate_text("  Hello  ", 10, strip=True)
        # Returns: ('Hello', False)
    """
    if limit < 0:
        raise ValueError(f"limit must be non-negative, got {limit}")
    
    text = value or ""
    if strip:
        text = text.strip()

    if len(text) <= limit:
        return text, False

    # For very short limits, just cut without ellipsis
    if limit <= 3:
        return text[:limit], True

    # Add ellipsis for truncation
    return f"{text[: limit - 3]}...", True


def strip_html(value: str | None, *, strip_whitespace: bool = False) -> str:
    """Remove HTML tags from text using lightweight regex-based stripping.

    This function uses a simple regex pattern to remove HTML tags. It is intended
    for preview/display purposes and is not meant to be an exhaustive HTML sanitizer.

    Args:
        value: Text containing HTML tags (None is treated as empty string)
        strip_whitespace: If True, strip leading/trailing whitespace from input

    Returns:
        Text with HTML tags replaced by spaces

    Examples:
        strip_html("<p>Hello</p>")
        # Returns: ' Hello '

        strip_html("<b>Bold</b> and <i>italic</i>")
        # Returns: ' Bold  and  italic '

        strip_html(None)
        # Returns: ''

        strip_html("  <p>Hello</p>  ", strip_whitespace=True)
        # Returns: ' Hello '

    Note:
        This is a lightweight HTML tag removal for previews and is not meant
        to be exhaustive or suitable for security-critical sanitization.
    """
    if not value:
        return ""

    text = value
    if strip_whitespace:
        text = text.strip()
        if not text:
            return ""

    # Replace HTML tags with spaces
    return _HTML_TAG_PATTERN.sub(" ", text)

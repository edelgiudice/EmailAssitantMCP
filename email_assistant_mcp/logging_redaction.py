"""Utilities for redacting sensitive data in logs."""

import re
from typing import Any


# Email pattern for redaction
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b')

# Sensitive keys that should be redacted
SENSITIVE_KEYS = {
    "access_token",
    "refresh_token",
    "client_secret",
    "app_password",
    "password",
    "token",
    "secret",
    "authorization",
    "credentials",
    "id_token",
    "bearer",
    "api_key",
    "api_secret",
    "private_key",
    "jwt",
    "auth_header",
}


def redact_email(email: str) -> str:
    """Redact email address username, keep domain.

    Args:
        email: Email address to redact

    Returns:
        Redacted email in format "***@domain.com"

    Examples:
        >>> redact_email("user@example.com")
        "***@example.com"
    """
    match = EMAIL_PATTERN.match(email)
    if match:
        return f"***@{match.group(1)}"
    return "***@***"


def redact_token(token: str, show_chars: int = 4) -> str:
    """Show only first and last N characters of a token.

    Args:
        token: Token to redact
        show_chars: Number of characters to show at start and end (default 4)

    Returns:
        Redacted token in format "abcd...wxyz"

    Examples:
        >>> redact_token("abcdefghijklmnop")
        "abcd...mnop"
    """
    if not token or len(token) <= show_chars * 2:
        return "***"
    return f"{token[:show_chars]}...{token[-show_chars:]}"


def redact_dict(data: dict[str, Any], sensitive_keys: set[str] | None = None) -> dict[str, Any]:
    """Recursively redact sensitive keys in a dictionary.

    Args:
        data: Dictionary to redact
        sensitive_keys: Set of keys to redact (defaults to SENSITIVE_KEYS)

    Returns:
        New dictionary with sensitive values redacted

    Examples:
        >>> redact_dict({"name": "John", "password": "secret123"})
        {"name": "John", "password": "***REDACTED***"}
    """
    if sensitive_keys is None:
        sensitive_keys = SENSITIVE_KEYS

    redacted = {}
    for key, value in data.items():
        if key.lower() in sensitive_keys:
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = redact_dict(value, sensitive_keys)
        elif isinstance(value, list):
            redacted[key] = [
                redact_dict(item, sensitive_keys) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[key] = value
    return redacted

"""Configuration schema for selecting and authenticating email providers."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Literal


@dataclass(slots=True)
class BaseEmailConfig:
    """Shared metadata every provider-specific config carries."""

    email_address: str
    display_name: str | None = None


@dataclass(slots=True)
class GmailOAuthConfig(BaseEmailConfig):
    """Configuration for Gmail using an OAuth refresh token."""

    provider: Literal["gmail"] = "gmail"
    refresh_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    token_uri: str = "https://oauth2.googleapis.com/token"
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587


EmailProviderConfig = GmailOAuthConfig


def _validate_email(email: str, field_name: str = "email_address") -> None:
    """Validate email address format."""
    if not isinstance(email, str) or not email:
        msg = f"Field '{field_name}' must be a non-empty string"
        raise ValueError(msg)
    # Basic email validation (not RFC-compliant, but catches obvious errors)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        msg = f"Field '{field_name}' has invalid email format: {email}"
        raise ValueError(msg)


def _validate_port(port: Any, field_name: str) -> None:
    """Validate port number is an integer in valid range."""
    if not isinstance(port, int):
        msg = f"Field '{field_name}' must be an integer, got {type(port).__name__}"
        raise ValueError(msg)
    if not (1 <= port <= 65535):
        msg = f"Field '{field_name}' must be between 1 and 65535, got {port}"
        raise ValueError(msg)


def _validate_required_string(value: Any, field_name: str) -> None:
    """Validate that a required string field is present and non-empty."""
    if not isinstance(value, str):
        msg = f"Field '{field_name}' must be a string, got {type(value).__name__}"
        raise ValueError(msg)
    if not value:
        msg = f"Field '{field_name}' cannot be empty"
        raise ValueError(msg)


def _validate_optional_string(value: Any, field_name: str) -> None:
    """Validate that an optional string field is a string if provided.

    Empty strings are explicitly allowed (for incomplete/partial configs).
    Only validates the type if a value is provided.
    """
    if not isinstance(value, str):
        msg = f"Field '{field_name}' must be a string, got {type(value).__name__}"
        raise ValueError(msg)


def email_config_from_dict(payload: Mapping[str, Any]) -> EmailProviderConfig:
    """Deserialize a plain dict coming from the LLM or a config file with validation.

    Validation behavior:
    - Required fields: provider, email_address (if provided)
    - Optional credential fields (refresh_token, client_id, client_secret, app_password):
      - Empty strings are explicitly allowed for incomplete/partial configs
      - These fields are optional at config-creation time but required for actual authentication
      - Type validation is enforced (must be strings if provided)
    - Port fields must be integers in range 1-65535 if provided

    This allows configs to be created and stored before all credentials are available,
    with authentication failing clearly at runtime if credentials are missing.
    """
    # Validate provider field
    provider = payload.get("provider")
    if not provider:
        msg = "Missing required field 'provider'"
        raise ValueError(msg)

    # Validate common required fields
    email_address = payload.get("email_address")
    if email_address is not None:
        _validate_email(email_address)

    # Provider-specific validation and instantiation
    if provider == "gmail":
        # Validate Gmail OAuth credentials (allow empty values for incomplete configs)
        # These fields are optional at config-creation time but required for actual authentication
        for field in ("refresh_token", "client_id", "client_secret"):
            if field in payload:
                _validate_optional_string(payload[field], field)

        # Validate port fields if present
        if "imap_port" in payload:
            _validate_port(payload["imap_port"], "imap_port")
        if "smtp_port" in payload:
            _validate_port(payload["smtp_port"], "smtp_port")

        return GmailOAuthConfig(**payload)

    msg = f"Unsupported email provider '{provider}'"
    raise ValueError(msg)


def email_config_to_dict(config: EmailProviderConfig) -> dict[str, Any]:
    """Serialize a config dataclass back into plain data."""
    return asdict(config)

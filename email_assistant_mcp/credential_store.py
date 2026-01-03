"""Persistence helpers for email provider configurations."""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Any, Dict, Mapping

from .config import EmailProviderConfig, email_config_from_dict, email_config_to_dict
from .logging_redaction import redact_email

logger = logging.getLogger(__name__)

DEFAULT_STORE_PATH = Path.home() / ".email_assistant_mcp" / "configs.json"


class CredentialNotFoundError(KeyError):
    """Raised when a config ID does not exist in the credential store."""


class CredentialStore:
    """JSON-backed store keyed by config IDs."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_STORE_PATH
        # File-based cache with mtime tracking
        self._cache_data: Dict[str, dict[str, Any]] | None = None
        self._cache_mtime: float | None = None

    @property
    def directory(self) -> Path:
        return self.path.parent

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid based on file mtime.

        Returns:
            True if cache is valid, False if file changed or cache is empty.
        """
        if self._cache_data is None or self._cache_mtime is None:
            return False

        if not self.path.exists():
            return False

        current_mtime = self.path.stat().st_mtime
        return current_mtime == self._cache_mtime

    def _check_file_permissions(self) -> None:
        """Check if credential file has secure permissions and warn if not."""
        try:
            file_stat = self.path.stat()
            mode = file_stat.st_mode
            # Check if file is readable/writable by group or others (insecure)
            if mode & (stat.S_IRWXG | stat.S_IRWXO):
                logger.warning(
                    "Credential file has insecure permissions | path=%s mode=%o | "
                    "Recommended: Set to 0600 (owner read/write only)",
                    self.path, stat.S_IMODE(mode)
                )
        except Exception as e:
            logger.debug("Could not check file permissions | path=%s error=%s", self.path, str(e))

    def _load_payloads(self) -> Dict[str, dict[str, Any]]:
        if not self.path.exists():
            logger.debug("Config store does not exist | path=%s", self.path)
            return {}

        # Check file permissions for security
        self._check_file_permissions()

        # Check cache
        if self._is_cache_valid():
            logger.debug("Using cached config store | path=%s", self.path)
            return self._cache_data  # type: ignore

        # Cache miss or file changed - load from disk
        try:
            logger.debug("Loading config store | path=%s", self.path)
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                msg = f"Credential store file '{self.path.name}' is corrupted"
                logger.error("Config store corrupted | path=%s", self.path)
                raise ValueError(msg)
            config_count = len(data)
            logger.debug("Config store loaded | path=%s config_count=%d", self.path, config_count)

            # Store in cache with mtime
            payloads = {str(k): dict(v) for k, v in data.items()}
            current_mtime = self.path.stat().st_mtime
            self._cache_data = payloads
            self._cache_mtime = current_mtime

            return payloads
        except json.JSONDecodeError as e:
            logger.error("Failed to parse config store | path=%s error=%s", self.path, str(e))
            raise

    def _write_payloads(self, payloads: Mapping[str, Mapping[str, Any]]) -> None:
        logger.debug("Writing config store | path=%s config_count=%d", self.path, len(payloads))
        self.directory.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payloads, indent=2)
        self.path.write_text(serialized, encoding="utf-8")

        # Set file permissions to 0600 (owner read/write only) for security
        try:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
            logger.debug("Set credential file permissions to 0600 | path=%s", self.path)
        except Exception as e:
            logger.warning("Failed to set file permissions | path=%s error=%s", self.path, str(e))

        # Invalidate cache after write
        self._cache_data = None
        self._cache_mtime = None
        logger.debug("Config store written successfully | path=%s", self.path)

    def list_config_ids(self) -> list[str]:
        """Return every config identifier stored on disk."""
        payloads = self._load_payloads()
        return sorted(payloads)

    def get_config(self, config_id: str) -> EmailProviderConfig:
        """Return the config dataclass for the requested ID."""
        logger.debug("Getting config | config_id=%s", config_id)
        payload = self.get_config_payload(config_id)
        config = email_config_from_dict(payload)
        logger.debug(
            "Config retrieved | config_id=%s provider=%s email=%s",
            config_id,
            getattr(config, "provider", "unknown"),
            redact_email(config.email_address)
        )
        return config

    def get_config_payload(self, config_id: str) -> dict[str, Any]:
        payloads = self._load_payloads()
        try:
            return dict(payloads[config_id])
        except KeyError as exc:
            logger.warning("Config not found | config_id=%s available_ids=%s", config_id, list(payloads.keys()))
            raise CredentialNotFoundError(config_id) from exc

    def save_config(self, config_id: str, config: EmailProviderConfig) -> None:
        logger.info(
            "Saving config | config_id=%s provider=%s email=%s",
            config_id,
            getattr(config, "provider", "unknown"),
            redact_email(config.email_address)
        )
        payloads = self._load_payloads()
        payloads[config_id] = email_config_to_dict(config)
        self._write_payloads(payloads)
        logger.info("Config saved successfully | config_id=%s", config_id)

    def delete_config(self, config_id: str) -> None:
        logger.info("Deleting config | config_id=%s", config_id)
        payloads = self._load_payloads()
        if config_id not in payloads:
            logger.warning("Cannot delete config - not found | config_id=%s", config_id)
            raise CredentialNotFoundError(config_id)
        del payloads[config_id]
        self._write_payloads(payloads)
        logger.info("Config deleted successfully | config_id=%s", config_id)

    def describe_config(self, config_id: str) -> dict[str, Any]:
        """Return non-sensitive metadata for the config.

        Note: Email addresses are redacted in the returned data for security.
        Use get_config() if you need the unredacted email address.
        """
        config = self.get_config(config_id)
        return {
            "config_id": config_id,
            "provider": getattr(config, "provider", "unknown"),
            "email_address": redact_email(config.email_address),
            "display_name": config.display_name,
        }

    @classmethod
    def default(cls) -> "CredentialStore":
        """Factory for the user's default store."""
        path = os.environ.get("EMAIL_ASSISTANT_CONFIG_STORE")
        store_path = Path(path) if path else DEFAULT_STORE_PATH
        logger.debug("Creating default credential store | path=%s", store_path)
        return cls(store_path if path else None)

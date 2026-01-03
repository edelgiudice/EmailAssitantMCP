"""Email provider client implementations."""

from .base import EmailClient
from .gmail_client import GmailClient

__all__ = ["EmailClient", "GmailClient"]

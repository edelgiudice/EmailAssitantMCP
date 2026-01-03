"""FastMCP server factory for the email assistant."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastmcp import FastMCP

from .credential_store import CredentialStore
from .logging_setup import configure_logging
from .tools import register_all_tools

logger = logging.getLogger(__name__)

SERVER_NAME = "email-assistant-mcp"
SERVER_INSTRUCTIONS = (
    "You are an email-focused personal assistant. "
    "IMPORTANT: This MCP server is a PROXY that provides access to email data and rule definitions—it does NOT automatically execute actions on emails. "
    "\n\n"
    "YOUR RESPONSIBILITY: When handling user requests (like 'manage today's emails'), you MUST: "
    "1. Call the appropriate tool (e.g., 'manage') to retrieve email messages and active rules as resources. "
    "   The 'manage' tool defaults to INBOX to avoid processing already-triaged messages. "
    "2. Read the returned resource:// URIs using resources/read to get the actual message and rule data. "
    "3. Analyze the messages against each active rule's criteria. "
    "4. CREATE AND EXECUTE A PLAN by calling the ref_command specified in each applicable rule. "
    "   Use 'batch_move_emails' for efficient bulk moves (supports different destinations per message). "
    "   Each message can be moved to a different folder in a single optimized batch operation. "
    "5. Provide a summary of all actions taken with success/failure breakdown. "
    "\n\n"
    "The 'manage' tool returns both messages AND rules, but calling it is only STEP 1. "
    "You must then EXECUTE each active rule's ref_command against matching messages to complete the triage cycle. "
    "\n\n"
    "BATCH OPERATIONS: Always use 'batch_move_emails' instead of individual move operations. "
    "Build a list of {message_id, destination_folder} operations and execute in one call for 50-100x performance improvement. "
    "\n\n"
    "Additional capabilities: Help with drafting responses, summarizing threads, organizing tasks, and managing automation rules. "
    "Reuse data exposed through MCP resources within the same session instead of reissuing duplicate tool calls."
)


def build_server() -> FastMCP[dict[str, str]]:
    """Create a FastMCP instance with the initial tool surface."""
    # Configure logging first - use environment variable or sensible default
    log_file = os.environ.get("EMAIL_ASSISTANT_LOG_FILE")
    if log_file:
        log_file = Path(log_file)
    else:
        # Default to user's home directory for cross-platform compatibility
        log_file = Path.home() / ".email_assistant_mcp" / "logs" / "server.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

    log_level = os.environ.get("EMAIL_ASSISTANT_LOG_LEVEL", "INFO")
    configure_logging(log_file=str(log_file), level=log_level)

    logger.info("Initializing email assistant MCP server | name=%s", SERVER_NAME)

    server = FastMCP(
        name=SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
    )

    logger.debug("Creating credential store")
    credential_store = CredentialStore.default()

    logger.debug("Registering tools")
    register_all_tools(server, credential_store)

    logger.info("Email assistant MCP server ready")

    return server

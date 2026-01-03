"""Tool registration helpers for the email assistant."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .bootstrap import register_bootstrap_tools
from .email_ops import register_email_ops_tools
from .folder import FolderTools
from .manage import ManageTools, register_manage_tools
from .messages import MessageTools, register_message_tools
from .rules import RuleStore, RuleTools, register_rule_tools

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..credential_store import CredentialStore


def register_all_tools(server: FastMCP, credential_store: CredentialStore) -> None:
    """Register every available tool set with the FastMCP server."""
    logger.info("Starting tool registration")

    logger.debug("Registering bootstrap tools")
    register_bootstrap_tools(server, credential_store)

    logger.debug("Registering email operations tools")
    folder_tools = FolderTools()
    register_email_ops_tools(server, credential_store)

    logger.debug("Registering message tools")
    message_tools = MessageTools()
    register_message_tools(server, credential_store, message_tools=message_tools)

    logger.debug("Registering rule tools")
    rule_store = RuleStore()
    rule_tools = RuleTools(rule_store=rule_store)
    register_rule_tools(server, rule_tools=rule_tools)

    logger.debug("Registering manage tools")
    manage_tools = ManageTools(
        message_tools=message_tools,
        rule_store=rule_store,
        folder_tools=folder_tools,
    )
    register_manage_tools(server, credential_store, manage_tools=manage_tools)

    logger.info("Tool registration completed | tool_sets=5")

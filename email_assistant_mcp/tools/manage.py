"""Combined email/rule management tool surface."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..utils.datetime_utils import utc_now
from .messages import MessageTools
from .rules import RuleStore, is_rule_active

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..credential_store import CredentialStore
    from .folder import FolderTools


class ManageTools:
    """Expose a helper tool that pairs mailbox results with rule guidance."""

    def __init__(
        self,
        *,
        message_tools: MessageTools,
        rule_store: RuleStore | None = None,
        folder_tools: "FolderTools | None" = None,
    ) -> None:
        self._message_tools = message_tools
        self._rule_store = rule_store or RuleStore()
        self._folder_tools = folder_tools

    def register(self, server: FastMCP, credential_store: CredentialStore) -> None:
        """Register the manage tool on the FastMCP server."""

        @server.tool(
            name="manage",
            description=(
                "STEP 1 of email triage workflow: Fetches email messages, active rule definitions, and available folders "
                "for a given date range. Provide config_id plus optional ISO 8601 from_date/to_date (defaults to today). "
                "\n\n"
                "CRITICAL: This tool only RETRIEVES data-it does NOT execute any actions. The tool response already includes "
                "messages (under 'messages'), rules (under 'rules'), and folders (under 'folders'). Use those fields directly; "
                "no additional MCP resource reads are required. After every manage call you MUST execute each rule in the "
                "'rules' list by running its ref_command against matching messages-without exception."
                "\n\n"
                "EMAIL TRIAGE WORKFLOW (PRIORITIZED): "
                "\n"
                "PRIORITY 1 - Apply Rules First: "
                "\n   - Check active_rule_count in the response. "
                "\n   - If active_rule_count > 0: For EACH active rule, evaluate which messages match its criteria and EXECUTE the rule's ref_command. "
                "\n   - Rules are your PRIMARY mechanism for moving messages-always apply them first before any other categorization. "
                "\n\n"
                "PRIORITY 2 - LLM-Based Folder Categorization (for remaining messages): "
                "\n   - After applying all rules, identify messages that were NOT processed by any rule. "
                "\n   - For these remaining messages, analyze their content and use LLM reasoning to categorize them. "
                "\n   - Review the 'folders' array to see available folders (both system and custom folders). "
                "\n   - Match messages to appropriate existing folders based on subject, sender, and content. "
                "\n   - Move categorized messages using move_emails tool with appropriate folder IDs. "
                "\n   - If no suitable folder exists and a clear category emerges, suggest creating a new folder to the user. "
                "\n\n"
                "FALLBACK - No Rules Configured: "
                "\n   - If active_rule_count = 0: Inform the user that no automation rules are configured. "
                "\n   - Suggest creating rules using create_rule for common patterns to automate future triage. "
                "\n   - You may still proceed with LLM-based folder categorization for the current batch if appropriate. "
                "\n\n"
                "IMPORTANT: By default, folder parameter is set to 'INBOX' which searches only untriaged inbox messages. "
                "DO NOT override the folder parameter unless the user explicitly requests searching a different folder or all folders. "
                "To search all folders, explicitly pass folder=None only when requested by the user. "
                "\n\n"
                "Response includes: request_id (for pagination), messages, rules, folders, and metadata. Use the request_id with "
                "get_emails to fetch additional pages if needed."
            ),
        )
        async def manage(
            config_id: str,
            *,
            from_date: str | None = None,
            to_date: str | None = None,
            folder: str | None = "INBOX",
        ) -> dict[str, Any]:
            resolved_from, resolved_to = self._resolve_date_range(from_date, to_date)
            logger.info(
                "Starting manage operation | config_id=%s from_date=%s to_date=%s folder=%s",
                config_id,
                resolved_from,
                resolved_to,
                folder or "all"
            )

            email_result = await self._message_tools.search_mailbox(
                server,
                credential_store,
                config_id,
                query=None,
                subject=None,
                sender=None,
                recipient=None,
                folder=folder,
                date_from=resolved_from,
                date_to=resolved_to,
            )

            logger.debug("Retrieving active rules | config_id=%s", config_id)
            rules_payload = self._active_rules_payload()

            # Fetch folder information if folder_tools is available
            folders_data: list[dict[str, Any]] = []
            folder_count = 0
            if self._folder_tools:
                logger.debug("Retrieving folder information | config_id=%s", config_id)
                try:
                    config = credential_store.get_config(config_id)
                    email_address = getattr(config, "email_address", None)
                    provider = getattr(config, "provider", None) or "unknown"

                    if email_address:
                        _, folders = self._folder_tools._sync_folder_resource(
                            server=server,
                            config=config,
                            config_id=config_id,
                            email_address=email_address,
                            provider=provider,
                        )
                        folder_count = len(folders)
                        folders_data = folders
                        logger.debug(
                            "Folders retrieved | config_id=%s folder_count=%d",
                            config_id,
                            folder_count
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to retrieve folders, continuing without folder information | config_id=%s error=%s",
                        config_id,
                        str(e)
                    )

            message_count = len(email_result.get("messages", []))
            active_rule_count = len(rules_payload["active_rules"])

            logger.info(
                "Manage operation completed | config_id=%s message_count=%d active_rule_count=%d folder_count=%d",
                config_id,
                message_count,
                active_rule_count,
                folder_count
            )

            combined = dict(email_result)
            combined.update(
                {
                    "from_date": resolved_from,
                    "to_date": resolved_to,
                    "active_rule_count": active_rule_count,
                    "rules": rules_payload["active_rules"],
                    "rules_generated_at": rules_payload["generated_at"],
                    "folder_count": folder_count,
                    "folders": folders_data,
                }
            )

            return combined

    def _resolve_date_range(self, from_date: str | None, to_date: str | None) -> tuple[str, str]:
        today = self._today_iso_date()
        resolved_from = (from_date or "").strip() or today
        resolved_to = (to_date or "").strip() or today
        return resolved_from, resolved_to

    def _active_rules_payload(self) -> dict[str, Any]:
        all_rules = self._rule_store.list_rules()
        active_rules = [rule.to_payload() for rule in all_rules if is_rule_active(rule)]
        return {
            "generated_at": utc_now().isoformat(),
            "active_rules": active_rules,
        }

    @staticmethod
    def _today_iso_date() -> str:
        return datetime.now(timezone.utc).date().isoformat()



def register_manage_tools(
    server: FastMCP,
    credential_store: CredentialStore,
    *,
    manage_tools: ManageTools | None = None,
) -> None:
    """Attach the Manage tool set to the FastMCP server."""
    if manage_tools is None:
        msg = "manage_tools instance is required to ensure message/rule state is shared."
        raise ValueError(msg)
    manage_tools.register(server, credential_store)

"""Rule management tools for FastMCP prompts."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence
from urllib.parse import quote

from pydantic import BaseModel, field_validator

from ..utils.datetime_utils import parse_iso8601_to_datetime, utc_now

if TYPE_CHECKING:
    from fastmcp import FastMCP

LOGGER = logging.getLogger(__name__)

# The repo root sits two levels up from this file: tools -> email_assistant_mcp -> root
DEFAULT_RULE_DIR = Path(__file__).resolve().parents[2] / "data" / "rules"
RULE_FILE_PATTERN = re.compile(r"^rule_(\d+)_")
SAFE_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


def _slugify(value: str) -> str:
    """Convert text to a filesystem-safe slug.

    Args:
        value: Text to slugify

    Returns:
        Filesystem-safe string with spaces/special chars replaced by underscores
    """
    value = (value or "").strip().replace(" ", "_")
    value = SAFE_CHARS.sub("_", value)
    value = value.strip("_")
    return value or "rule"


class RuleRecord(BaseModel):
    """Validated representation of a rule."""

    id: int
    name: str
    summary: str
    ref_command: str
    version: int
    prompt: str
    expiration_date: str | None = None
    auto_execute: bool = False

    @field_validator("name", "summary", "ref_command", mode="before")
    @classmethod
    def strip_and_validate_string(cls, v: Any) -> str:
        """Strip whitespace and ensure non-empty."""
        stripped = str(v).strip()
        if not stripped:
            raise ValueError("must be non-empty")
        return stripped

    @field_validator("prompt", mode="before")
    @classmethod
    def validate_prompt(cls, v: Any) -> str:
        """Ensure prompt is non-empty."""
        prompt = str(v)
        if not prompt:
            raise ValueError("must be non-empty")
        return prompt

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        """Ensure version is positive."""
        if v < 1:
            raise ValueError("must be a positive integer")
        return v

    @field_validator("expiration_date", mode="before")
    @classmethod
    def normalize_expiration(cls, v: Any) -> str | None:
        """Convert expiration_date to string or None."""
        return str(v) if v is not None else None

    def to_payload(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return self.model_dump()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, expected_id: int | None = None) -> "RuleRecord":
        """Validate and construct a rule from a raw mapping."""
        rule = cls.model_validate(payload)
        if expected_id is not None and expected_id != rule.id:
            msg = f"Rule ID mismatch: file expects {expected_id}, payload has {rule.id}"
            raise ValueError(msg)
        return rule

    def filename(self) -> str:
        """Return the filename for this rule."""
        return f"rule_{self.id}_{_slugify(self.ref_command)}_{_slugify(self.name)}.json"


def is_rule_active(rule: RuleRecord, *, now: datetime | None = None) -> bool:
    """Determine whether a rule is still active at the given time."""
    if rule.expiration_date is None:
        return True
    effective_now = now or utc_now()
    expiration = parse_iso8601_to_datetime(rule.expiration_date, normalize_to_utc=True)
    return expiration > effective_now


class RuleStore:
    """File-backed rule persistence."""

    def __init__(self, *, rules_dir: Path | str | None = None) -> None:
        """Initialize RuleStore with optional custom rules directory.

        Args:
            rules_dir: Optional path to rules directory (defaults to data/rules/)
        """
        self.rules_dir = Path(rules_dir) if rules_dir else DEFAULT_RULE_DIR

    def next_rule_id(self) -> int:
        """Return the next available rule ID.

        Scans existing rule files and returns max(existing_ids) + 1,
        or 1 if no rules exist.

        Returns:
            Next available integer ID for a new rule
        """
        ids = self._existing_rule_ids()
        return (max(ids) + 1) if ids else 1

    def list_rules(self) -> list[RuleRecord]:
        """Load every rule from disk."""
        if not self.rules_dir.exists():
            return []
        rules = []
        for path in sorted(self.rules_dir.glob("rule_*.json")):
            rules.append(self._load_rule_file(path))
        return rules

    def load_rule(self, rule_id: int) -> RuleRecord:
        path = self._path_for_rule(rule_id)
        return self._load_rule_file(path)

    def save_rule(self, rule: RuleRecord, *, previous_path: Path | None = None) -> Path:
        """Persist a rule to disk, renaming if needed."""
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        target = self.rules_dir / rule.filename()
        serialized = json.dumps(rule.to_payload(), indent=2)
        temp_path = target.with_suffix(".json.tmp")
        temp_path.write_text(serialized, encoding="utf-8")
        temp_path.replace(target)
        if previous_path and previous_path != target and previous_path.exists():
            previous_path.unlink()
        return target

    def _existing_rule_ids(self) -> list[int]:
        if not self.rules_dir.exists():
            return []
        ids = []
        for path in self.rules_dir.glob("rule_*.json"):
            ids.append(self._parse_rule_id(path))
        return ids

    def _path_for_rule(self, rule_id: int) -> Path:
        if not self.rules_dir.exists():
            msg = f"Rule '{rule_id}' does not exist."
            raise FileNotFoundError(msg)
        matches = sorted(self.rules_dir.glob(f"rule_{rule_id}_*.json"))
        if not matches:
            msg = f"Rule '{rule_id}' does not exist."
            raise FileNotFoundError(msg)
        return matches[0]

    def _load_rule_file(self, path: Path) -> RuleRecord:
        rule_id = self._parse_rule_id(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            msg = f"Rule file '{path.name}' is not a JSON object."
            raise ValueError(msg)
        return RuleRecord.from_payload(payload, expected_id=rule_id)

    @staticmethod
    def _parse_rule_id(path: Path) -> int:
        match = RULE_FILE_PATTERN.match(path.name)
        if not match:
            msg = f"Rule file name '{path.name}' is invalid."
            raise ValueError(msg)
        return int(match.group(1))


DEFAULT_META_PROMPTS: list[dict[str, str]] = [
    {
        "name": "rules_meta_guidance",
        "description": "How to propose rule data for the email assistant.",
        "content": (
            "You can create and maintain automation rules that are tied to specific MCP commands. "
            "When proposing a rule, supply: name, summary, ref_command (a known MCP tool name), "
            "prompt text, and optional expiration_date (ISO 8601). Prefer descriptive names and "
            "set expiration when the rule is temporary. The server stores rules as JSON files named "
            "rule_<id>_<ref_command>_<name>.json and bumps version on edits. "
            "Rules are controlled by expiration_date: if null/None, the rule remains active indefinitely; "
            "if set to a future date, the rule remains valid until that date expires. "
            "Use set_rule_expiration to change a rule's expiration status at any time."
        ),
    },
]


class RuleTools:
    """High-level coordinator for rule management."""

    def __init__(
        self,
        *,
        rule_store: RuleStore | None = None,
        meta_prompts: Sequence[Mapping[str, str]] | None = None,
    ) -> None:
        self._rule_store = rule_store or RuleStore()
        self._meta_prompts = list(meta_prompts) if meta_prompts is not None else DEFAULT_META_PROMPTS

    def register(self, server: FastMCP) -> None:
        """Attach rule tools and prompts to the FastMCP server."""
        self._register_meta_prompts(server)
        self._register_create_rule_tool(server)
        self._register_edit_rule_tool(server)
        self._register_set_rule_expiration_tool(server)
        self._register_get_rules_tool(server)

    def _register_create_rule_tool(self, server: FastMCP) -> None:
        @server.tool(
            name="create_rule",
            description=(
                "Create a new rule JSON file scoped to a specific MCP command. Pass auto_execute=true when the rule "
                "should run the referenced command automatically during manage() flows."
            ),
        )
        async def create_rule(
            name: str,
            summary: str,
            ref_command: str,
            prompt: str,
            expiration_date: str | None = None,
            auto_execute: bool = False,
        ) -> dict[str, Any]:
            name, summary, ref_command, prompt = self._validated_required_fields(
                name=name,
                summary=summary,
                ref_command=ref_command,
                prompt=prompt,
            )
            normalized_expiration = self._validate_expiration(expiration_date)
            await self._assert_known_command(ref_command, server)

            rule_id = self._rule_store.next_rule_id()
            rule = RuleRecord(
                id=rule_id,
                name=name,
                summary=summary,
                ref_command=ref_command,
                version=1,
                prompt=prompt,
                expiration_date=normalized_expiration,
                auto_execute=bool(auto_execute),
            )
            self._rule_store.save_rule(rule)
            sync_result = self._refresh_resources(server)
            return {
                "rule": rule.to_payload(),
                "resource_uri": sync_result["resources"].get(ref_command),
                "index_resource": sync_result["index_resource"],
            }

    def _register_edit_rule_tool(self, server: FastMCP) -> None:
        @server.tool(
            name="edit_rule",
            description=(
                "Modify an existing rule and bump its version. Use the auto_execute parameter to toggle whether manage() "
                "should execute the referenced command automatically."
            ),
        )
        async def edit_rule(
            rule_id: int,
            name: str | None = None,
            summary: str | None = None,
            ref_command: str | None = None,
            prompt: str | None = None,
            expiration_date: str | None = None,
            auto_execute: bool | None = None,
        ) -> dict[str, Any]:
            current, current_path = self._load_rule_with_path(rule_id)
            updates = self._apply_rule_updates(
                current=current,
                name=name,
                summary=summary,
                ref_command=ref_command,
                prompt=prompt,
                expiration_date=expiration_date,
                auto_execute=auto_execute,
            )
            await self._assert_known_command(updates.ref_command, server)
            updated = RuleRecord(
                id=current.id,
                name=updates.name,
                summary=updates.summary,
                ref_command=updates.ref_command,
                version=current.version + 1,
                prompt=updates.prompt,
                expiration_date=updates.expiration_date,
                auto_execute=updates.auto_execute,
            )
            self._rule_store.save_rule(updated, previous_path=current_path)
            sync_result = self._refresh_resources(server)
            return {
                "rule": updated.to_payload(),
                "resource_uri": sync_result["resources"].get(updated.ref_command),
                "index_resource": sync_result["index_resource"],
            }

    def _register_set_rule_expiration_tool(self, server: FastMCP) -> None:
        @server.tool(
            name="set_rule_expiration",
            description=(
                "Set or remove the expiration date for a rule and bump its version. "
                "If expiration_date is null/None, the rule remains active indefinitely. "
                "If expiration_date is set to an ISO 8601 date, the rule remains valid until that date expires."
            ),
        )
        async def set_rule_expiration(rule_id: int, expiration_date: str | None = None) -> dict[str, Any]:
            current, current_path = self._load_rule_with_path(rule_id)
            parsed = self._validate_expiration(expiration_date)
            updated = RuleRecord(
                id=current.id,
                name=current.name,
                summary=current.summary,
                ref_command=current.ref_command,
                version=current.version + 1,
                prompt=current.prompt,
                expiration_date=parsed,
                auto_execute=current.auto_execute,
            )
            self._rule_store.save_rule(updated, previous_path=current_path)

            status = "active indefinitely" if parsed is None else f"active until {parsed}"
            sync_result = self._refresh_resources(server)
            return {
                "rule": updated.to_payload(),
                "status": status,
                "resource_uri": sync_result["resources"].get(updated.ref_command),
                "index_resource": sync_result["index_resource"],
            }

    def _register_get_rules_tool(self, server: FastMCP) -> None:
        @server.tool(
            name="get_rules",
            description="Return active rules grouped by MCP command and refresh rule resources.",
        )
        async def get_rules() -> dict[str, Any]:
            sync_result = self._refresh_resources(server)
            commands: dict[str, Any] = {}
            for ref_command, prompts in sync_result["grouped"].items():
                commands[ref_command] = {
                    "resource_uri": sync_result["resources"].get(ref_command),
                    "prompt_count": len(prompts),
                    "prompts": prompts,
                }
            return {
                "active_rule_count": len(sync_result["active_rules"]),
                "commands": commands,
                "index_resource": sync_result["index_resource"],
            }

    def _load_rule_with_path(self, rule_id: int) -> tuple[RuleRecord, Path]:
        try:
            path = self._rule_store._path_for_rule(int(rule_id))
        except (FileNotFoundError, ValueError) as exc:
            msg = f"Rule '{rule_id}' does not exist."
            raise ValueError(msg) from exc
        return self._rule_store._load_rule_file(path), path

    def _validate_expiration(self, expiration_date: str | None) -> str | None:
        if expiration_date is None:
            return None
        parsed = parse_iso8601_to_datetime(expiration_date, normalize_to_utc=True)
        return parsed.isoformat()

    @staticmethod
    def _validated_required_fields(
        *,
        name: str,
        summary: str,
        ref_command: str,
        prompt: str,
    ) -> tuple[str, str, str, str]:
        name = (name or "").strip()
        summary = (summary or "").strip()
        ref_command = (ref_command or "").strip()
        prompt = (prompt or "").strip()
        if not all((name, summary, ref_command, prompt)):
            msg = "Fields 'name', 'summary', 'ref_command', and 'prompt' are required."
            raise ValueError(msg)
        return name, summary, ref_command, prompt

    async def _assert_known_command(self, ref_command: str, server: FastMCP) -> None:
        tools = await server.get_tools()
        if ref_command not in tools:
            msg = f"Unknown ref_command '{ref_command}'. Known tools: {', '.join(sorted(tools))}"
            raise ValueError(msg)

    def _apply_rule_updates(
        self,
        *,
        current: RuleRecord,
        name: str | None,
        summary: str | None,
        ref_command: str | None,
        prompt: str | None,
        expiration_date: str | None,
        auto_execute: bool | None,
    ) -> RuleRecord:
        updated_name = (name or current.name).strip()
        updated_summary = (summary or current.summary).strip()
        updated_ref_command = (ref_command or current.ref_command).strip()
        updated_prompt = (prompt or current.prompt).strip()
        parsed_expiration = (
            self._validate_expiration(expiration_date)
            if expiration_date is not None
            else current.expiration_date
        )
        resolved_auto_execute = current.auto_execute if auto_execute is None else bool(auto_execute)

        if not updated_name or not updated_summary or not updated_ref_command or not updated_prompt:
            msg = "Updated values cannot be empty."
            raise ValueError(msg)

        return RuleRecord(
            id=current.id,
            name=updated_name,
            summary=updated_summary,
            ref_command=updated_ref_command,
            version=current.version,
            prompt=updated_prompt,
            expiration_date=parsed_expiration,
            auto_execute=resolved_auto_execute,
        )

    def _refresh_resources(self, server: FastMCP) -> dict[str, Any]:
        all_rules = self._rule_store.list_rules()
        active_rules = [rule for rule in all_rules if self._is_active(rule)]
        grouped = self._group_by_command(active_rules)
        resource_map: dict[str, str] = {}
        ref_commands = sorted({rule.ref_command for rule in all_rules})

        for ref_command in ref_commands:
            prompts = grouped.get(ref_command, [])
            uri = self._resource_uri(ref_command)
            self._register_prompt_resource(
                server=server,
                resource_uri=uri,
                ref_command=ref_command,
                prompts=prompts,
            )
            resource_map[ref_command] = uri

        index_uri = self._register_index_resource(server, all_rules)

        return {
            "grouped": grouped,
            "resources": resource_map,
            "index_resource": index_uri,
            "active_rules": active_rules,
        }

    def _group_by_command(self, rules: Iterable[RuleRecord]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for rule in rules:
            grouped.setdefault(rule.ref_command, []).append(self._prompt_payload(rule))
        return grouped

    @staticmethod
    def _prompt_payload(rule: RuleRecord) -> dict[str, Any]:
        return {
            "id": rule.id,
            "name": rule.name,
            "summary": rule.summary,
            "version": rule.version,
            "prompt": rule.prompt,
            "expiration_date": rule.expiration_date,
            "auto_execute": rule.auto_execute,
        }

    @staticmethod
    def _resource_uri(ref_command: str) -> str:
        safe_command = quote(ref_command, safe="")
        return f"resource://rules/prompts/{safe_command}"

    def _register_prompt_resource(
        self,
        *,
        server: FastMCP,
        resource_uri: str,
        ref_command: str,
        prompts: Sequence[Mapping[str, Any]],
    ) -> None:
        payload = {
            "ref_command": ref_command,
            "prompts": list(prompts),
        }

        def _read_resource() -> str:
            return json.dumps(payload, indent=2)

        server.resource(
            resource_uri,
            name=f"prompts/{ref_command}",
            description=f"Active rule prompts for '{ref_command}'",
            mime_type="application/json",
        )(_read_resource)

    def _register_index_resource(self, server: FastMCP, all_rules: Sequence[RuleRecord]) -> str:
        resource_uri = "resource://rules/index"
        payload = {
            "rules": [rule.to_payload() for rule in all_rules],
        }

        def _read_resource() -> str:
            return json.dumps(payload, indent=2)

        server.resource(
            resource_uri,
            name="rules/index",
            description="All rule definitions (active and inactive).",
            mime_type="application/json",
        )(_read_resource)
        return resource_uri

    def _is_active(self, rule: RuleRecord, *, now: datetime | None = None) -> bool:
        return is_rule_active(rule, now=now)

    def _register_meta_prompts(self, server: FastMCP) -> None:
        """Expose static prompts to help the LLM craft rule content."""
        for prompt_def in self._meta_prompts:
            name = prompt_def.get("name")
            description = prompt_def.get("description")
            content = prompt_def.get("content")
            if not name or not content:
                LOGGER.warning("Skipping invalid meta prompt definition: %s", prompt_def)
                continue

            @server.prompt(name=name, description=description)
            def _meta_prompt(content: str = content) -> list[dict[str, str]]:
                return [
                    {"role": "system", "content": content},
                    {
                        "role": "assistant",
                        "content": (
                            "When creating or editing a rule, always provide a clear name, summary, "
                            "ref_command, prompt text, and expiration_date when applicable."
                        ),
                    },
                ]


def register_rule_tools(
    server: FastMCP,
    *,
    rule_tools: RuleTools | None = None,
) -> None:
    """Attach rule tools to the FastMCP server."""

    if rule_tools is None:
        rule_tools = RuleTools()

    rule_tools.register(server)

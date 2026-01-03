"""Tests for the rule management tools."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from email_assistant_mcp.tools import rules
from tests.helpers import ToolCapturingFastMCP


class RuleToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.rules_path = Path(self.tmp_dir.name)
        self.server = ToolCapturingFastMCP()
        # Seed known tools so ref_command validation passes
        self.server.tools["create_email_folder"] = lambda *args, **kwargs: None
        self.server.tools["list_email_folders"] = lambda *args, **kwargs: None
        self.rule_tools = rules.RuleTools(rule_store=rules.RuleStore(rules_dir=self.rules_path))
        rules.register_rule_tools(self.server, rule_tools=self.rule_tools)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def run_tool(self, tool_name: str, *args: Any, **kwargs: Any) -> Any:
        tool = self.server.tools[tool_name]
        return asyncio.run(tool(*args, **kwargs))

    def test_create_rule_persists_and_registers_resources(self) -> None:
        expiration = "2030-01-31T00:00:00Z"
        result = self.run_tool(
            "create_rule",
            name="Trip To India",
            summary="Collect travel communications.",
            ref_command="create_email_folder",
            prompt="Route trip emails into TripToIndia folder.",
            expiration_date=expiration,
            auto_execute=True,
        )

        files = list(self.rules_path.glob("rule_*.json"))
        self.assertEqual(len(files), 1)
        stored = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(stored["name"], "Trip To India")
        self.assertEqual(stored["version"], 1)
        self.assertTrue(stored["auto_execute"])
        self.assertIn("create_email_folder", files[0].name)
        self.assertEqual(result["rule"]["expiration_date"], "2030-01-31T00:00:00+00:00")
        self.assertTrue(result["rule"]["auto_execute"])

        resource_uri = result["resource_uri"]
        resource = self.server.resources[resource_uri]
        payload = json.loads(asyncio.run(resource.read()))
        self.assertEqual(payload["ref_command"], "create_email_folder")
        self.assertEqual(len(payload["prompts"]), 1)
        self.assertEqual(payload["prompts"][0]["name"], "Trip To India")
        self.assertTrue(payload["prompts"][0]["auto_execute"])

    def test_get_rules_filters_expired(self) -> None:
        self.run_tool(
            "create_rule",
            name="Active rule",
            summary="Stay active.",
            ref_command="create_email_folder",
            prompt="Do active things.",
            expiration_date=None,
        )
        self.run_tool(
            "create_rule",
            name="Expired rule",
            summary="Should not show.",
            ref_command="create_email_folder",
            prompt="Old prompt.",
            expiration_date="2020-01-01T00:00:00Z",
        )

        result = self.run_tool("get_rules")
        commands = result["commands"]["create_email_folder"]
        self.assertEqual(commands["prompt_count"], 1)
        self.assertEqual(commands["prompts"][0]["name"], "Active rule")

    def test_edit_rule_bumps_version_and_renames_file(self) -> None:
        created = self.run_tool(
            "create_rule",
            name="Receipt filing",
            summary="File receipts.",
            ref_command="create_email_folder",
            prompt="File receipts prompt.",
            expiration_date=None,
        )
        rule_id = created["rule"]["id"]

        edited = self.run_tool(
            "edit_rule",
            rule_id=rule_id,
            name="Receipt filing updated",
            ref_command="list_email_folders",
            prompt="Updated prompt body.",
            auto_execute=True,
        )

        files = list(self.rules_path.glob("rule_*.json"))
        self.assertEqual(len(files), 1)
        self.assertIn("list_email_folders", files[0].name)
        stored = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(stored["version"], 2)
        self.assertTrue(stored["auto_execute"])
        self.assertEqual(edited["rule"]["version"], 2)
        self.assertEqual(edited["rule"]["ref_command"], "list_email_folders")
        self.assertTrue(edited["rule"]["auto_execute"])

    def test_meta_prompts_registered(self) -> None:
        self.assertIn("rules_meta_guidance", self.server.prompts)
        self.assertEqual(len(self.server.prompts), len(rules.DEFAULT_META_PROMPTS))

    def test_set_rule_expiration_with_date(self) -> None:
        created = self.run_tool(
            "create_rule",
            name="System cleanup",
            summary="Collect cleanup reminders.",
            ref_command="create_email_folder",
            prompt="Route cleanup emails.",
            expiration_date=None,
        )
        activation_date = "2032-05-01T00:00:00Z"

        updated = self.run_tool("set_rule_expiration", rule_id=created["rule"]["id"], expiration_date=activation_date)

        files = list(self.rules_path.glob("rule_*.json"))
        self.assertEqual(len(files), 1)
        stored = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(stored["expiration_date"], "2032-05-01T00:00:00+00:00")
        self.assertFalse(stored["auto_execute"])
        self.assertEqual(updated["rule"]["version"], 2)
        self.assertFalse(updated["rule"]["auto_execute"])
        self.assertEqual(updated["status"], "active until 2032-05-01T00:00:00+00:00")

    def test_set_rule_expiration_to_indefinite(self) -> None:
        created = self.run_tool(
            "create_rule",
            name="Quarterly reports",
            summary="Handle reports.",
            ref_command="create_email_folder",
            prompt="Send to reports folder.",
            expiration_date="2035-01-01T00:00:00Z",
        )

        updated = self.run_tool("set_rule_expiration", rule_id=created["rule"]["id"], expiration_date=None)

        files = list(self.rules_path.glob("rule_*.json"))
        self.assertEqual(len(files), 1)
        stored = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertIsNone(stored["expiration_date"])
        self.assertFalse(stored["auto_execute"])
        self.assertEqual(updated["rule"]["version"], 2)
        self.assertFalse(updated["rule"]["auto_execute"])
        self.assertEqual(updated["status"], "active indefinitely")


class RuleStoreFileTests(unittest.TestCase):
    """Integration tests against a shared fixture directory."""

    FIXTURE_DIR = Path(__file__).resolve().parent.parent / "rules"

    def setUp(self) -> None:
        self.rules_path = self.FIXTURE_DIR
        self.rules_path.mkdir(parents=True, exist_ok=True)
        self._cleanup_rules()

    def tearDown(self) -> None:
        self._cleanup_rules()

    def _cleanup_rules(self) -> None:
        for path in self.rules_path.glob("rule_*.json"):
            path.unlink()

    def test_rule_store_raises_error_for_non_json_object(self) -> None:
        """Test that loading a rule file with non-object JSON raises error with sanitized message."""
        # Create a rule file with a JSON array instead of object
        fixture_path = self.rules_path / "rule_99_test_command_invalid.json"
        fixture_path.write_text("[]", encoding="utf-8")

        store = rules.RuleStore(rules_dir=self.rules_path)

        with self.assertRaises(ValueError) as ctx:
            store.list_rules()

        # Verify error message uses only filename, not full path
        error_msg = str(ctx.exception)
        self.assertIn(fixture_path.name, error_msg)
        self.assertNotIn(str(fixture_path.parent), error_msg)
        self.assertEqual(error_msg, f"Rule file '{fixture_path.name}' is not a JSON object.")

    def test_rule_store_lists_existing_rules_from_fixture_dir(self) -> None:
        payload = {
            "id": 7,
            "name": "Fixture rule",
            "summary": "Ensure fixture directory works.",
            "ref_command": "create_email_folder",
            "version": 3,
            "prompt": "Use the fixture folder.",
            "expiration_date": None,
        }
        fixture_path = self.rules_path / "rule_7_create_email_folder_fixture_rule.json"
        fixture_path.write_text(json.dumps(payload), encoding="utf-8")

        store = rules.RuleStore(rules_dir=self.rules_path)

        stored_rules = store.list_rules()
        self.assertEqual(len(stored_rules), 1)
        rule = stored_rules[0]
        self.assertEqual(rule.id, 7)
        self.assertEqual(rule.name, "Fixture rule")
        self.assertEqual(rule.version, 3)
        self.assertFalse(rule.auto_execute)

        next_id = store.next_rule_id()
        self.assertEqual(next_id, 8)


if __name__ == "__main__":
    unittest.main()

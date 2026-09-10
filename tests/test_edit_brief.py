"""Tests for edit brief generation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_ENGINE = Path(__file__).resolve().parent.parent
if str(SCRIPT_ENGINE) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ENGINE))

from src.edit_brief import (  # noqa: E402
    attach_edit_briefs,
    build_edit_brief,
    format_edit_brief_markdown,
    format_edit_brief_telegram,
    project_id_from_script,
)


SAMPLE = {
    "script_number": 1,
    "title_overlay": "CURSOR WAS BILLING ME TWICE",
    "filename_hint": "script_01_cursor_was_billing_me.mp4",
    "estimated_seconds": 49,
    "opening_line": "Cursor was sending my entire chat history on every single request.",
    "recording_tip": "Hit 'that's insane' like genuine annoyance.",
    "spoken_script": "Cursor was sending my entire chat history. That's insane.",
    "hook_visual": {
        "tier": "higgsfield",
        "prompt": "Cursor IDE Settings panel, Models tab, toggle highlighted",
        "why": "Prove the settings move exists",
    },
    "visual_briefs": [
        {
            "tier": "fal",
            "at_phrase": "Go to Cursor Settings",
            "prompt": "Cursor IDE settings screen, Models tab open",
        },
        {"tier": "remotion", "type": "stat", "display": "40%", "label": "API BILL DROP"},
    ],
    "visual_moments": [
        {"at_phrase": "that's insane", "type": "reaction"},
        {"at_phrase": "forty percent", "type": "stat", "graphic": "40%", "label": "API BILL DROP"},
    ],
    "custom_visual_overrides": [
        {
            "trigger_phrase": "my dashboard",
            "description": "Screenshot of billing dashboard",
            "asset_status": "needs_creation",
        }
    ],
}


class TestEditBrief(unittest.TestCase):
    def test_project_id_from_filename_hint(self):
        self.assertEqual(
            project_id_from_script(SAMPLE),
            "script_01_cursor_was_billing_me",
        )

    def test_build_includes_talking_head_and_captures(self):
        brief = build_edit_brief(SAMPLE)
        self.assertEqual(brief["project_id"], "script_01_cursor_was_billing_me")
        self.assertTrue(brief["talking_head"]["required"])
        self.assertGreaterEqual(len(brief["captures"]), 2)
        self.assertTrue(any(c["required"] for c in brief["captures"]))
        self.assertTrue(any("40%" in x for x in brief["auto_handled"]))

    def test_markdown_has_drop_paths(self):
        md = format_edit_brief_markdown(build_edit_brief(SAMPLE))
        self.assertIn("script_01_cursor_was_billing_me", md)
        self.assertIn("inbox/", md)
        self.assertIn("assets/", md)
        self.assertIn("Remotion handles automatically", md)

    def test_telegram_compact(self):
        msg = format_edit_brief_telegram(build_edit_brief(SAMPLE))
        self.assertIn("CAPTURE LIST", msg)
        self.assertIn("Record", msg)

    def test_attach_edit_briefs(self):
        scripts = [{**SAMPLE}]
        attach_edit_briefs(scripts)
        self.assertIn("edit_brief", scripts[0])
        self.assertEqual(scripts[0]["edit_brief"]["project_id"], "script_01_cursor_was_billing_me")


if __name__ == "__main__":
    unittest.main()

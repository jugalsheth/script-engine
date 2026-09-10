"""Tests for corpus edit recipe picker."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_ENGINE = Path(__file__).resolve().parent.parent
if str(SCRIPT_ENGINE) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ENGINE))

from src.edit_recipes import apply_recipe_to_script, pick_recipe_id  # noqa: E402


class TestEditRecipes(unittest.TestCase):
    def test_hack_defaults_to_face_hook_screen_proof(self):
        script = {
            "script_type": "HACK",
            "hook_type": "OPEN LOOP",
            "spoken_script": "Cursor was billing me twice. Here's the toggle.",
            "title_overlay": "CURSOR BILL FIX",
        }
        self.assertEqual(pick_recipe_id(script), "FACE_HOOK_SCREEN_PROOF")

    def test_confession_gets_confession_stat(self):
        script = {
            "script_type": "CONFESSION",
            "hook_type": "CONFESSION",
            "spoken_script": "I burned my API bill. Here's the fix.",
        }
        self.assertEqual(pick_recipe_id(script), "CONFESSION_STAT")

    def test_walkthrough_detected_from_spoken(self):
        script = {
            "script_type": "HACK",
            "hook_type": "OPEN LOOP",
            "spoken_script": "Download the zip, go to settings, upload the skill.",
            "title_overlay": "CLAUDE SKILL INSTALL",
        }
        self.assertEqual(pick_recipe_id(script), "WALKTHROUGH")

    def test_apply_sets_edit_recipe_block(self):
        script = {
            "script_type": "TIP",
            "hook_type": "OPEN LOOP",
            "spoken_script": "One Cursor setting saves tokens.",
            "hook_visual": {
                "tier": "fal",
                "prompt": "purple AI brain glowing neon network futuristic HUD",
            },
        }
        apply_recipe_to_script(script)
        self.assertEqual(script["edit_template"], "FACE_HOOK_SCREEN_PROOF")
        self.assertEqual(script["edit_recipe"]["id"], "FACE_HOOK_SCREEN_PROOF")
        prompt = script["hook_visual"]["prompt"].lower()
        self.assertIn("product ui", prompt)
        self.assertNotIn("purple", prompt)
        self.assertNotIn("neon network", prompt)

    def test_legacy_three_step_maps_away(self):
        script = {
            "script_type": "TIP",
            "edit_template": "THREE_STEP_HOT_TAKE",
            "spoken_script": "One tip about Claude Code.",
        }
        self.assertEqual(pick_recipe_id(script), "FACE_HOOK_SCREEN_PROOF")


if __name__ == "__main__":
    unittest.main()

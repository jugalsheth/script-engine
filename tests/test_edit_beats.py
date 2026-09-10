"""Tests for script-engine edit_beats stamping."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_ENGINE = Path(__file__).resolve().parent.parent
if str(SCRIPT_ENGINE) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ENGINE))

from src.edit_beats import apply_edit_beats, derive_edit_beats  # noqa: E402
from src.edit_recipes import apply_recipe_to_script  # noqa: E402


class TestEditBeats(unittest.TestCase):
    def test_derive_hook_triple_from_script_fields(self):
        script = {
            "opening_line": "Cursor was billing me twice.",
            "title_overlay": "CURSOR BILL FIX",
            "hook_visual": {"tier": "fal", "asset_file": "hook_hero.png"},
            "open_loop_plant": "here's the toggle",
            "edit_template": "FACE_HOOK_SCREEN_PROOF",
            "visual_briefs": [
                {"tier": "fal", "at_phrase": "settings toggle", "prompt": "settings UI"},
            ],
            "video_triggers": {
                "beat_phrases": {"crust": "here's the thing", "payoff": "one click"},
            },
        }
        beats = derive_edit_beats(script)
        self.assertEqual(beats["hook_triple"]["verbal"], "Cursor was billing me twice.")
        self.assertEqual(beats["hook_triple"]["written"], "CURSOR BILL FIX")
        self.assertEqual(beats["hook_triple"]["visual"], "hook_hero.png")
        self.assertEqual(beats["rehook_at"], "here's the toggle")
        self.assertEqual(beats["proof_at"], "settings toggle")
        self.assertEqual(beats["receipt_at"], "one click")

    def test_apply_is_idempotent(self):
        script = {
            "opening_line": "I burned tokens.",
            "title_overlay": "TOKEN FIX",
            "spoken_script": "I burned tokens. That's insane. Here's the fix.",
            "edit_template": "CONFESSION_STAT",
        }
        apply_edit_beats(script)
        first = dict(script["edit_beats"])
        apply_edit_beats(script)
        self.assertEqual(script["edit_beats"], first)

    def test_recipe_apply_then_beats(self):
        script = {
            "script_type": "HACK",
            "hook_type": "OPEN LOOP",
            "spoken_script": "Cursor was billing me twice. Here's the toggle.",
            "title_overlay": "CURSOR BILL FIX",
            "opening_line": "Cursor was billing me twice.",
        }
        apply_recipe_to_script(script)
        apply_edit_beats(script)
        self.assertEqual(script["edit_recipe"]["id"], "FACE_HOOK_SCREEN_PROOF")
        self.assertIn("hook_triple", script["edit_beats"])
        self.assertTrue(script["edit_beats"]["hook_triple"]["written"])


if __name__ == "__main__":
    unittest.main()

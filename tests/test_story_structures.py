"""Tests for viral story-structure batch assignment + slogan ban."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_ENGINE = Path(__file__).resolve().parent.parent
if str(SCRIPT_ENGINE) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ENGINE))

from src.generator import (  # noqa: E402
    FUN_PHRASE_POOL,
    FORMAT_MIX_ORDER,
    STORY_STRUCTURES,
    _resolve_batch_script_types,
    _resolve_batch_story_structures,
)
from src.script_validator import validate_script  # noqa: E402


class TestStoryStructures(unittest.TestCase):
    def test_eight_pack_covers_all_doors(self):
        types = list(FORMAT_MIX_ORDER)  # 8 slots
        structures = _resolve_batch_story_structures(types)
        self.assertEqual(len(structures), 8)
        present = set(structures)
        for door in STORY_STRUCTURES:
            self.assertIn(door, present, f"missing {door} in {structures}")

    def test_confession_and_build_are_kitchen(self):
        structures = _resolve_batch_story_structures(
            ["CONFESSION", "BUILD", "HACK", "TIP"]
        )
        self.assertEqual(structures[0], "KITCHEN_NIGHTMARES")
        self.assertEqual(structures[1], "KITCHEN_NIGHTMARES")

    def test_news_is_shark(self):
        structures = _resolve_batch_story_structures(
            ["ACTIONABLE_NEWS", "HACK", "TIP", "HOT_TAKE"]
        )
        self.assertEqual(structures[0], "SHARK_TANK")
        self.assertEqual(structures[3], "SHARK_TANK")

    def test_topics_resolve_types_then_structures(self):
        topics = [{"source_type": "trend", "format_hint": "hack"} for _ in range(8)]
        types = _resolve_batch_script_types(topics)
        structures = _resolve_batch_story_structures(types)
        self.assertEqual(len(types), 8)
        self.assertEqual(len(set(structures)), 3)

    def test_pure_building_not_in_fun_pool(self):
        self.assertNotIn("pure building", FUN_PHRASE_POOL.lower())

    def test_banned_pure_building_in_spoken(self):
        script = {
            "spoken_script": (
                "Cursor agent mode was eating tokens. Here's the thing — "
                "drop a .cursorrules file. Pure building. Try it today."
            ),
            "opening_line": "Cursor agent mode was eating tokens.",
            "loopback_closer": "Try it today.",
            "open_loop_plant": "Here's the thing",
            "title_overlay": "ONE FILE FIXED IT",
            "hook_mode": "complementary",
            "script_type": "HACK",
            "story_structure": "MAP",
            "hook_visual": {"tier": "higgsfield", "prompt": "Cursor rules file"},
            "video_triggers": {
                "fun_phrases": ["here's the thing", "try it today"],
                "beat_phrases": {"crust": "here's the thing", "payoff": "try it today"},
                "broll_phrases": [],
                "broll_image_descriptions": [],
            },
        }
        result = validate_script(script, {"source_type": "trend"})
        banned = [e for e in result.errors if "Banned phrase" in e or "pure building" in e.lower()]
        self.assertTrue(banned, f"expected ban hit, got errors={result.errors}")


if __name__ == "__main__":
    unittest.main()

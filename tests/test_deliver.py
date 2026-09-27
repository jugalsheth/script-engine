"""Tests for Telegram delivery formatting."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_ENGINE = Path(__file__).resolve().parent.parent
if str(SCRIPT_ENGINE) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ENGINE))

from src.deliver import (  # noqa: E402
    _format_minimal_script,
    _format_spoken_readable,
    build_telegram_messages,
    format_teleprompter,
    get_delivery_mode,
)


SAMPLE_SCRIPT = {
    "script_number": 3,
    "territory": "AI Demystified",
    "hook_type": "CONFESSION",
    "story_structure": "KITCHEN_NIGHTMARES",
    "title_overlay": "WHY CURSOR FEELS WORTH IT",
    "spoken_script": (
        "I overspent on Cursor again this month. Twenty bucks over Pro. "
        "That's not a billing problem. That's a product design lesson."
    ),
    "filename_hint": "script_03_cursor_is_worth_the.mp4",
    "estimated_seconds": 52,
    "source_type": "journal",
    "source": "journal",
}


class TestDeliverFormatting(unittest.TestCase):
    def test_spoken_readable_splits_sentences(self):
        result = _format_spoken_readable("First line. Second line! Third?")
        self.assertIn("First line.", result)
        self.assertIn("Second line!", result)
        self.assertIn("Third?", result)
        self.assertEqual(result.count("\n"), 2)

    def test_teleprompter_short_lines_and_pauses(self):
        spoken = (
            "I overspent on Cursor again this month. "
            "Twenty bucks over Pro felt insane. "
            "That's the move — check the usage panel today."
        )
        tp = format_teleprompter(spoken)
        self.assertIn("\n\n", tp)
        for block in tp.split("\n\n"):
            for line in block.split("\n"):
                self.assertLessEqual(len(line.split()), 8)
                self.assertLessEqual(len(line), 40)

    def test_minimal_script_contains_teleprompter_pre(self):
        msg = _format_minimal_script(SAMPLE_SCRIPT)
        self.assertIn("SCRIPT 3", msg)
        self.assertIn("AI Demystified", msg)
        self.assertIn("KITCHEN_NIGHTMARES", msg)
        self.assertIn("WHY CURSOR FEELS WORTH IT", msg)
        self.assertIn("TELEPROMPTER", msg)
        self.assertIn("<pre>", msg)
        self.assertIn("</pre>", msg)
        self.assertIn("script_03_cursor_is_worth_the.mp4", msg)
        self.assertIn("~52s", msg)
        self.assertNotIn("VISUAL CUES", msg)
        self.assertNotIn("RECORDING SHEET", msg)

    def test_minimal_batch_message_count(self):
        scripts = [
            {**SAMPLE_SCRIPT, "script_number": 1, "source_type": "journal"},
            {
                **SAMPLE_SCRIPT,
                "script_number": 2,
                "source_type": "story",
                "source": "trending",
            },
            {
                **SAMPLE_SCRIPT,
                "script_number": 3,
                "source_type": "trend",
                "source": "trending",
            },
        ]
        messages = build_telegram_messages(scripts, delivery_mode="minimal")
        self.assertEqual(len(messages), 4)  # header + 3 scripts
        self.assertIn("1 personal", messages[0])
        self.assertIn("1 story", messages[0])
        self.assertIn("1 evergreen", messages[0])

    def test_full_mode_includes_recording_sheet(self):
        scripts = [SAMPLE_SCRIPT]
        messages = build_telegram_messages(
            scripts,
            topics_researched=5,
            topics_dropped=1,
            delivery_mode="full",
        )
        self.assertEqual(len(messages), 4)  # header + sheet + script + footer
        self.assertIn("RECORDING SHEET", messages[1])
        self.assertIn("TELEPROMPTER", messages[2])
        self.assertIn("VISUAL CUES", messages[2])

    def test_get_delivery_mode_defaults_minimal(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(get_delivery_mode(), "minimal")

    def test_get_delivery_mode_full(self):
        with mock.patch.dict("os.environ", {"TELEGRAM_DELIVERY": "full"}):
            self.assertEqual(get_delivery_mode(), "full")


if __name__ == "__main__":
    unittest.main()

"""Tests for story quality scoring."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_ENGINE = Path(__file__).resolve().parent.parent
if str(SCRIPT_ENGINE) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ENGINE))

from src.script_validator import STORY_SCORE_THRESHOLD, score_story_quality  # noqa: E402


BLAND_SCRIPT = {
    "script_type": "STORY_REACTION",
    "hook_type": "IDENTITY CALL",
    "spoken_script": (
        "Step one — open three job posts today. "
        "Step two — learn Spark this week. "
        "Step three — deploy an Airflow DAG. "
        "According to this week's report, SQL is in demand."
    ),
}

STORY_SCRIPT = {
    "script_type": "STORY_REACTION",
    "hook_type": "CONFESSION",
    "spoken_script": (
        "I felt betrayed when my pipeline failed at 2am — fourteen days of free trial, gone. "
        "Turns out the mailer API was the weak link. "
        "I switched to a manual fallback in thirty seconds. "
        "That's how you pivot when production breaks."
    ),
}


class TestStoryQuality(unittest.TestCase):
    def test_journal_always_scores_high(self):
        topic = {"source_type": "journal"}
        self.assertEqual(score_story_quality(BLAND_SCRIPT, topic), 100)

    def test_bland_listicle_scores_low(self):
        topic = {"source_type": "story", "story_hook": "pipeline failed"}
        score = score_story_quality(BLAND_SCRIPT, topic)
        self.assertLess(score, STORY_SCORE_THRESHOLD)

    def test_narrative_script_scores_high(self):
        topic = {
            "source_type": "story",
            "story_hook": "pipeline failed",
            "tension": "free trial expired",
        }
        score = score_story_quality(STORY_SCRIPT, topic)
        self.assertGreaterEqual(score, STORY_SCORE_THRESHOLD)


if __name__ == "__main__":
    unittest.main()

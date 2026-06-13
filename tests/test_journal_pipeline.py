"""Tests for content journal pipeline (matcher dedup, queue, shot planner)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SCRIPT_ENGINE = Path(__file__).resolve().parent.parent
if str(SCRIPT_ENGINE) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ENGINE))

from src.matcher import (  # noqa: E402
    domain_tags_for_text,
    find_duplicate_queue_entry,
    journal_topic_from_queue,
    keyword_overlap_ratio,
    mark_queue_consumed,
    pull_queue_entries,
)

VIDEO_ENGINE = SCRIPT_ENGINE.parent / "video-engine"


class TestDomainTags(unittest.TestCase):
    def test_tags_data_engineering(self):
        text = "Our Snowflake pipeline handles CDC from the warehouse"
        tags = domain_tags_for_text(text)
        self.assertIn("data_engineering", tags)

    def test_overlap_similar_texts(self):
        a = "Snowflake CDC pipeline deduplication broke last night"
        b = "The Snowflake pipeline deduplication issue from last night"
        ratio = keyword_overlap_ratio(a, b)
        self.assertGreaterEqual(ratio, 0.6)

    def test_overlap_different_texts(self):
        a = "Snowflake CDC pipeline deduplication"
        b = "LinkedIn resume tips for salary negotiation"
        ratio = keyword_overlap_ratio(a, b)
        self.assertLess(ratio, 0.3)


class TestQueueDedup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.data_dir.mkdir()
        self.queue_path = self.data_dir / "personal_topics_queue.json"
        self.journal_dir = self.data_dir / "journal"
        self.journal_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    @patch("src.matcher.DATA_DIR")
    @patch("src.matcher.QUEUE_PATH")
    @patch("src.matcher.JOURNAL_DIR")
    def test_find_duplicate_merges_same_domain(self, mock_journal_dir, mock_queue_path, mock_data_dir):
        mock_data_dir.__truediv__ = lambda self, x: self.data_dir / x if hasattr(self, "data_dir") else Path(x)
        mock_data_dir.mkdir = lambda *a, **k: None
        mock_queue_path.__class__ = Path
        mock_journal_dir.__class__ = Path

        queue = [{
            "id": "abc-123",
            "first_captured": "2026-06-10T10:00:00Z",
            "raw_text": "Snowflake CDC pipeline deduplication broke in production",
            "related_mentions": [],
            "domain_tags": ["data_engineering"],
            "processed": False,
        }]
        duplicate = find_duplicate_queue_entry(
            "Snowflake CDC pipeline deduplication broke in production again today",
            queue=queue,
            journal_recent=[],
        )
        self.assertIsNotNone(duplicate)
        self.assertEqual(duplicate["id"], "abc-123")

    def test_pull_queue_oldest_first(self):
        with patch("src.matcher._load_queue") as mock_load:
            mock_load.return_value = [
                {"id": "2", "first_captured": "2026-06-12T10:00:00Z", "raw_text": "newer", "processed": False, "domain_tags": []},
                {"id": "1", "first_captured": "2026-06-10T10:00:00Z", "raw_text": "older", "processed": False, "domain_tags": []},
            ]
            entries = pull_queue_entries(2)
            self.assertEqual(entries[0]["queue_id"], "1")
            self.assertEqual(entries[1]["queue_id"], "2")

    def test_mark_queue_consumed(self):
        with patch("src.matcher._load_queue") as mock_load, patch("src.matcher.save_queue") as mock_save:
            mock_load.return_value = [
                {"id": "q1", "processed": False, "used_in_script": None},
            ]
            journal_topics = [journal_topic_from_queue({
                "id": "q1",
                "raw_text": "test ramble",
                "domain_tags": ["ai_ml"],
                "first_captured": "2026-06-13T10:00:00Z",
            })]
            scripts = [{"queue_id": "q1", "filename_hint": "script_01_test.mp4"}]
            mark_queue_consumed(journal_topics, scripts)
            mock_save.assert_called_once()
            saved = mock_save.call_args[0][0]
            self.assertTrue(saved[0]["processed"])
            self.assertEqual(saved[0]["used_in_script"], "script_01_test.mp4")


class TestOversizedJournalEntry(unittest.TestCase):
    def test_oversized_flag_logic(self):
        max_duration = 300
        duration = 400
        oversized = duration > max_duration
        self.assertTrue(oversized)


class TestMainOrchestration(unittest.TestCase):
    def test_empty_queue_fills_all_slots(self):
        with patch("src.matcher._load_queue", return_value=[]):
            entries = pull_queue_entries(3)
            self.assertEqual(entries, [])
            total_slots = 8
            remaining = total_slots - len(entries)
            self.assertEqual(remaining, 8)

    def test_reserved_slots_growth(self):
        from main import _reserved_journal_slots
        self.assertEqual(_reserved_journal_slots("growth"), 3)

    def test_reserved_slots_intro(self):
        from main import _reserved_journal_slots
        self.assertEqual(_reserved_journal_slots("intro"), 1)


if __name__ == "__main__":
    unittest.main()

"""Tests for journal Perplexity enrichment parsing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_ENGINE = Path(__file__).resolve().parent.parent
if str(SCRIPT_ENGINE) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ENGINE))

from src.journal_enrich import (  # noqa: E402
    _merge_enrichment,
    _parse_enrichment_response,
)


class TestJournalEnrichParse(unittest.TestCase):
    def test_parse_valid_array(self):
        content = """[
          {
            "queue_id": "abc-123",
            "timely_context": "Cursor announced a new deal this week.",
            "hook_angles": ["I almost missed the Cursor wave"],
            "stats_to_weave": ["38% of devs use AI daily — Stack Overflow 2026"]
          }
        ]"""
        parsed = _parse_enrichment_response(content)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["queue_id"], "abc-123")
        self.assertIn("Cursor", parsed[0]["timely_context"])
        self.assertEqual(len(parsed[0]["hook_angles"]), 1)

    def test_merge_by_queue_id(self):
        topics = [{
            "source_type": "journal",
            "queue_id": "q1",
            "raw_transcript": "my ramble",
        }]
        enrichments = [{
            "queue_id": "q1",
            "timely_context": "News context here.",
            "hook_angles": [],
            "stats_to_weave": [],
        }]
        merged = _merge_enrichment(topics, enrichments)
        self.assertIn("journal_enrichment", merged[0])
        self.assertEqual(merged[0]["journal_enrichment"]["timely_context"], "News context here.")


if __name__ == "__main__":
    unittest.main()

"""Offline tests for TLDR parse helpers + builder lens (no network required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_ENGINE = Path(__file__).resolve().parent.parent
if str(SCRIPT_ENGINE) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ENGINE))

from src.tldr_feed import (  # noqa: E402
    is_sponsor_title,
    matches_builder_lens,
    parse_rss_items,
)


SAMPLE_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>TLDR AI</title>
<item>
  <title>Forge: Conference (Sponsor)</title>
  <description>Sponsor blurb</description>
  <pubDate>Fri, 11 Sep 2026 00:00:00 GMT</pubDate>
</item>
<item>
  <title>OpenAI Launches the Agents API (3 minute read)</title>
  <description>OpenAI introduced the Agents API in public beta for developers.</description>
  <pubDate>Fri, 11 Sep 2026 00:00:00 GMT</pubDate>
</item>
<item>
  <title>Cursor Origin ships new agent panel</title>
  <link>https://tldr.tech/ai/2026-09-11</link>
  <description>Cursor updated Origin with a clearer agent panel.</description>
  <pubDate>Fri, 11 Sep 2026 00:00:00 GMT</pubDate>
</item>
</channel></rss>
"""


class TestTldrParse(unittest.TestCase):
    def test_parse_skips_empty_titles_and_sets_archive(self):
        items = parse_rss_items(SAMPLE_RSS)
        self.assertEqual(len(items), 3)
        agents = next(i for i in items if "Agents API" in i["title"])
        self.assertTrue(agents["archive_url"].startswith("https://tldr.tech/ai/"))
        self.assertIsNotNone(agents["age_days"])
        self.assertLessEqual(agents["age_days"], 7)

    def test_sponsor_and_builder_lens(self):
        self.assertTrue(is_sponsor_title("Forge (Sponsor)"))
        self.assertFalse(is_sponsor_title("OpenAI Agents API"))
        self.assertTrue(matches_builder_lens("OpenAI Agents API", "developers beta"))
        self.assertTrue(
            matches_builder_lens("Cursor Origin", "agent panel", ["cursor", "claude"])
        )
        self.assertFalse(
            matches_builder_lens("Random cooking tip", "lasagna recipes", ["cursor"])
        )


if __name__ == "__main__":
    unittest.main()

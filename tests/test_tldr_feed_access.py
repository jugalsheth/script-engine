"""Live accessibility gate for TLDR AI feeds.

Run before wiring TLDR into community research:
  python3 -m unittest tests.test_tldr_feed_access -v
"""

from __future__ import annotations

import unittest

import httpx

from src.tldr_feed import (
    TLDR_AI_ARCHIVE,
    TLDR_AI_RSS_FALLBACK,
    TLDR_AI_RSS_PRIMARY,
    USER_AGENT,
    is_sponsor_title,
    parse_rss_items,
    probe_feed,
)

# Soft freshness: newest story should be within this many days
MAX_AGE_DAYS = 7


class TestTldrFeedAccess(unittest.TestCase):
    """Live network checks — proves cron can reach TLDR."""

    def test_at_least_one_rss_feed_is_fully_usable(self):
        results = []
        for url in (TLDR_AI_RSS_PRIMARY, TLDR_AI_RSS_FALLBACK):
            results.append(probe_feed(url))

        usable = [r for r in results if r["ok"]]
        self.assertTrue(
            usable,
            f"No TLDR RSS feed usable. Probes: {results}",
        )

        best = max(usable, key=lambda r: (r["story_count"], -r.get("age_days", 999)))
        self.assertGreaterEqual(
            best["story_count"],
            1,
            f"Usable feed has no non-sponsor stories: {best}",
        )
        age = best.get("age_days")
        if age is not None:
            self.assertLessEqual(
                age,
                MAX_AGE_DAYS,
                f"Newest TLDR item is stale ({age}d). Prefer a fresher mirror. {best}",
            )
        print(f"\n   TLDR gate OK via {best['url']} ({best['story_count']} stories, age={age}d)")

    def test_daily_archive_page_reachable(self):
        """Optional backup surface (same content as Gmail 'View Online')."""
        with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30.0) as client:
            resp = client.get(TLDR_AI_ARCHIVE)
        self.assertEqual(resp.status_code, 200, TLDR_AI_ARCHIVE)
        self.assertIn("tldr", resp.text.lower())
        self.assertGreater(len(resp.text), 1000)

    def test_parse_rss_items_helper_on_live_body(self):
        with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30.0) as client:
            resp = client.get(TLDR_AI_RSS_PRIMARY)
            if resp.status_code != 200:
                resp = client.get(TLDR_AI_RSS_FALLBACK)
        self.assertEqual(resp.status_code, 200)
        items = parse_rss_items(resp.content)
        self.assertGreaterEqual(len(items), 1)
        non_sponsor = [i for i in items if not is_sponsor_title(i["title"])]
        self.assertGreaterEqual(len(non_sponsor), 1)
        sample = non_sponsor[0]
        self.assertTrue(sample["title"].strip())
        # link may be empty on some mirrors — archive_url or summary must exist
        self.assertTrue(sample.get("link") or sample.get("archive_url") or sample.get("summary"))


if __name__ == "__main__":
    unittest.main()

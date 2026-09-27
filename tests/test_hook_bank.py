"""Tests for hook bank + content calendar."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_ENGINE = Path(__file__).resolve().parent.parent
if str(SCRIPT_ENGINE) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ENGINE))

from src import hook_bank  # noqa: E402


class TestHookBank(unittest.TestCase):
    def test_bank_has_all_58(self):
        bank = hook_bank.load_bank()
        self.assertEqual(len(bank.get("hooks") or []), 58)
        ids = {h["id"] for h in bank["hooks"]}
        self.assertEqual(len(ids), 58)

    def test_calendar_covers_all_hook_ids(self):
        cal = hook_bank.load_calendar()
        slots = cal.get("slots") or []
        self.assertEqual(len(slots), 58)
        ids = {s["hook_id"] for s in slots}
        self.assertEqual(len(ids), 58)
        weeks = {s["week"] for s in slots}
        self.assertEqual(weeks, set(range(1, 9)))

    def test_week1_mix_cap(self):
        topics = hook_bank.topics_for_week(1)
        self.assertGreaterEqual(len(topics), 6)
        tipish = hook_bank.tip_ish_count(topics)
        self.assertLessEqual(tipish, 5)
        for t in topics:
            self.assertEqual(t["seed_origin"], "calendar")
            self.assertEqual(t["source_platform"], "hook_bank")
            self.assertTrue(t.get("hook_bank_id"))
            self.assertEqual(t["estimated_virality"], "manual")

    def test_write_override(self):
        topics = hook_bank.topics_for_week(1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "topics_override.txt"
            with mock.patch.object(hook_bank, "OVERRIDE_PATH", path):
                out = hook_bank.write_override(topics, week=1)
            text = out.read_text(encoding="utf-8")
            self.assertIn("Calendar week 1", text)
            self.assertIn(topics[0]["topic_title"][:40], text)
            # comments shouldn't be empty of hooks
            lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
            self.assertEqual(len(lines), len(topics))

    def test_hook_to_topic_adaptation(self):
        hook = {
            "id": "hook_99",
            "hook": "Test viral hook about Cursor costs",
            "pillar": "production_ai",
            "format_hint": "tip",
            "series_arc": "prod_ai_leaks_2026w38",
            "adaptation_note": "Pin model in Cursor",
            "status": "queued",
        }
        topic = hook_bank.hook_to_topic(hook, {"week": 1, "slot": 1, "script_type": "TIP"})
        self.assertIn("Pin model", topic["topic_summary"])
        self.assertEqual(topic["format_hint"], "tip")
        self.assertEqual(topic["hook_bank_id"], "hook_99")

    def test_history_apis_do_not_touch_formal_bank(self):
        """Regression: generator needs get_recent_hooks/save_hooks; formal bank stays object."""
        bank_before = json.loads(hook_bank.BANK_PATH.read_text(encoding="utf-8"))
        self.assertIsInstance(bank_before, dict)
        self.assertEqual(len(bank_before.get("hooks") or []), 58)

        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "hook_history.json"
            history.write_text(
                json.dumps(
                    [
                        {"opening_line": "Old hook A", "hook_type": "OPEN LOOP", "date": "2026-01-01"},
                        {"opening_line": "Old hook B", "hook_type": "CONFESSION", "date": "2026-01-02"},
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(hook_bank, "HISTORY_PATH", history):
                with mock.patch.object(hook_bank, "DATA_DIR", Path(tmp)):
                    recent = hook_bank.get_recent_hooks(30)
                    self.assertEqual(recent, ["Old hook A", "Old hook B"])
                    hook_bank.save_hooks(
                        [
                            {"opening_line": "Old hook B", "hook_type": "X"},
                            {"opening_line": "Brand new opening", "hook_type": "Y"},
                        ]
                    )
                    recent2 = hook_bank.get_recent_hooks(30)
                    self.assertEqual(recent2[-1], "Brand new opening")
                    self.assertEqual(len(recent2), 3)

        bank_after = json.loads(hook_bank.BANK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(bank_after, bank_before)
        self.assertTrue(hasattr(hook_bank, "get_recent_hooks"))
        self.assertTrue(hasattr(hook_bank, "save_hooks"))


if __name__ == "__main__":
    unittest.main()

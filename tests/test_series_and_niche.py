"""Tests for series calendar + vibe niche matching."""

from __future__ import annotations

from datetime import date

from src.series_calendar import (
    filter_topics_for_series,
    get_active_series,
    series_keyword_boost,
    stamp_script_series,
)
from src.matcher import score_topics
from src.research import FALLBACK_TOPICS, _normalize_topic


def test_active_series_loaded():
    series = get_active_series(today=date(2026, 7, 23))
    assert series is not None
    assert "cursor" in " ".join(series.get("theme_keywords") or []).lower() or "claude" in str(
        series.get("theme_keywords")
    ).lower()


def test_series_keyword_boost():
    series = {
        "theme_keywords": ["cursor", "claude code", "mcp"],
    }
    assert series_keyword_boost("Claude Code + Higgsfield MCP mashup", series) >= 2
    assert series_keyword_boost("random cooking recipe", series) == 0


def test_filter_topics_for_series_prefers_on_arc():
    series = {"theme_keywords": ["cursor", "mcp"]}
    topics = [
        {"topic_title": "Cursor MCP hack", "topic_summary": "wire mcp"},
        {"topic_title": "AWS interview tips", "topic_summary": "hiring managers"},
        {"topic_title": "Claude Code tip", "topic_summary": "terminal"},
    ]
    filtered = filter_topics_for_series(topics, max_off_arc=1, series=series)
    titles = [t["topic_title"] for t in filtered]
    assert titles[0] == "Cursor MCP hack"
    assert "AWS interview tips" in titles  # allowed as off-arc budget
    assert len(filtered) <= 3


def test_stamp_script_series():
    series = {
        "id": "test_arc",
        "title": "Cursor Deep",
        "episode_count_target": 6,
        "theme_keywords": ["cursor"],
    }
    script = stamp_script_series({}, 3, series)
    assert script["series_id"] == "test_arc"
    assert script["series_note"] == "Cursor Deep · Ep 3/6"
    assert script["episode_index"] == 3


def test_fallback_topics_are_vibe_coding():
    blob = " ".join(t["topic_title"] for t in FALLBACK_TOPICS).lower()
    assert "cursor" in blob or "claude" in blob
    assert "hiring manager" not in blob


def test_normalize_hack_source_type():
    t = _normalize_topic(
        {
            "topic_title": "Hack: Claude Code + Higgsfield",
            "topic_summary": "mashup",
            "source_type": "hack",
            "estimated_virality": "high",
        },
        "social",
    )
    assert t is not None
    assert t["source_type"] == "hack"


def test_matcher_scores_cursor_higher_than_aws_career():
    topics = [
        {
            "topic_title": "Cursor agent mode overspend fix",
            "topic_summary": "token bill in Cursor Composer",
        },
        {
            "topic_title": "How to stand out in data engineering interviews",
            "topic_summary": "hiring managers and LinkedIn recruiters",
        },
    ]
    scored = score_topics(topics)
    by_title = {t["topic_title"]: t["match_score"] for t in scored}
    assert by_title["Cursor agent mode overspend fix"] >= by_title[
        "How to stand out in data engineering interviews"
    ]

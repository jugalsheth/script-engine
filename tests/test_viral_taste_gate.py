"""ViralTasteGate + hero inject smoke tests."""

from __future__ import annotations

from src.script_validator import validate_script
from src.generator import _resolve_batch_script_types, FORMAT_MIX_ORDER, _normalize_script


def _base_script(**overrides):
    s = {
        "spoken_script": (
            "Open Cursor and flip agent mode on — that's the move. "
            "Here's the thing: most people stay in chat and waste tokens. Wrong. "
            "Run one parallel agent on the failing test and ship in ten minutes. "
            "That's all it is."
        ),
        "opening_line": "Open Cursor and flip agent mode on — that's the move.",
        "loopback_closer": "That's all it is.",
        "script_type": "HACK",
        "hook_type": "OPEN LOOP",
        "video_triggers": {
            "fun_phrases": ["wrong", "that's all it is"],
            "beat_phrases": {"crust": "here's the thing"},
            "stat_phrases": [],
            "broll_phrases": [],
            "energy_words": ["wrong", "truth"],
        },
        "visual_moments": [],
        "hook_visual": {
            "tier": "higgsfield",
            "prompt": "9:16 Cursor agent panel",
            "duration_s": 2.5,
        },
        "series_note": "Cursor + Claude Mashups · Ep 1/8",
    }
    s.update(overrides)
    return s


def test_viral_gate_passes_good_hack():
    result = validate_script(_base_script(), {"source_type": "social"})
    assert result.passed, result.errors


def test_viral_gate_rejects_hn_points_hook():
    script = _base_script(
        spoken_script=(
            "Browser MCP just hit six hundred points on Hacker News — and it's wild. "
            "You install one MCP. Right? That's all it is."
        ),
        opening_line="Browser MCP just hit six hundred points on Hacker News — and it's wild.",
        loopback_closer="That's all it is.",
        script_type="HACK",
    )
    result = validate_script(script, {"source_type": "social"})
    assert not result.passed
    assert any("HN point" in e or "ViralTasteGate" in e for e in result.errors)


def test_viral_gate_rejects_missing_move():
    script = _base_script(
        spoken_script=(
            "Claude Code is changing everything for builders this week. "
            "Everyone is talking about agents. Right? That's all it is."
        ),
        opening_line="Claude Code is changing everything for builders this week.",
        loopback_closer="That's all it is.",
    )
    # strip fun/beat still present
    result = validate_script(script, {"source_type": "social"})
    assert not result.passed
    assert any("copyable move" in e for e in result.errors)


def test_format_mix_order():
    topics = [{"topic_title": f"t{i}", "source_type": "social"} for i in range(8)]
    types = _resolve_batch_script_types(topics)
    assert types == FORMAT_MIX_ORDER


def test_normalize_forces_higgsfield_on_hack():
    script = _normalize_script(
        {
            "script_type": "HACK",
            "title_overlay": "TEST",
            "spoken_script": "Open Cursor. Wrong. Truth.",
            "hook_visual": {"tier": "fal", "prompt": "x"},
            "video_triggers": {},
        }
    )
    assert script["hook_visual"]["tier"] == "higgsfield"
    assert len(script["video_triggers"]["fun_phrases"]) >= 2
    assert script["video_triggers"]["beat_phrases"].get("crust")

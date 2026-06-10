from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PHASE_CONFIG = CONFIG_DIR / "content_phase.txt"
STATE_PATH = DATA_DIR / "publish_state.json"
INTRO_THRESHOLD = 4


def _ensure_state() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        STATE_PATH.write_text('{"videos_published": 0}\n', encoding="utf-8")
        return {"videos_published": 0}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"videos_published": 0}
    except (OSError, json.JSONDecodeError):
        return {"videos_published": 0}


def get_videos_published() -> int:
    return int(_ensure_state().get("videos_published", 0))


def get_phase() -> str:
    """Return 'intro' or 'growth' based on publish count and config override."""
    try:
        override = PHASE_CONFIG.read_text(encoding="utf-8").strip().lower()
    except OSError:
        override = "intro"

    if override == "growth":
        return "growth"
    if get_videos_published() >= INTRO_THRESHOLD:
        return "growth"
    return "intro"


def get_phase_label() -> str:
    published = get_videos_published()
    if get_phase() == "intro":
        return f"INTRO — {published}/4 videos published"
    return "GROWTH — full power mode"

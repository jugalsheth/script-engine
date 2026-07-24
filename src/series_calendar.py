"""Active series calendar — rotating 2–3 week arcs inside the vibe-coding niche."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CALENDAR_PATH = CONFIG_DIR / "series_calendar.json"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def load_calendar() -> dict:
    try:
        return json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"⚠️ Could not read series_calendar.json: {exc}")
        return {"active_series_id": None, "series": [], "mashup_watchlist": []}


def save_calendar(data: dict) -> None:
    CALENDAR_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_active_series(today: date | None = None) -> dict | None:
    """Return the active series, rotating by end_date / episode target when needed."""
    today = today or date.today()
    data = load_calendar()
    series_list = data.get("series") or []
    if not series_list:
        return None

    by_id = {s.get("id"): s for s in series_list if s.get("id")}
    active_id = data.get("active_series_id")
    active = by_id.get(active_id) if active_id else None

    if active and _series_still_open(active, today):
        return active

    for s in series_list:
        start = _parse_date(s.get("start_date"))
        end = _parse_date(s.get("end_date"))
        if start and end and start <= today <= end:
            if data.get("active_series_id") != s["id"]:
                data["active_series_id"] = s["id"]
                save_calendar(data)
            return s

    if active:
        ids = [s.get("id") for s in series_list]
        try:
            idx = ids.index(active["id"])
            nxt = series_list[(idx + 1) % len(series_list)]
        except ValueError:
            nxt = series_list[0]
        data["active_series_id"] = nxt["id"]
        save_calendar(data)
        return nxt

    first = series_list[0]
    data["active_series_id"] = first["id"]
    save_calendar(data)
    return first


def _series_still_open(series: dict, today: date) -> bool:
    end = _parse_date(series.get("end_date"))
    if end and today > end:
        return False
    target = int(series.get("episode_count_target") or 0)
    done = int(series.get("episodes_completed") or 0)
    if target and done >= target:
        return False
    return True


def series_keyword_boost(text: str, series: dict | None = None) -> int:
    series = series or get_active_series()
    if not series:
        return 0
    text_lower = text.lower()
    return sum(1 for kw in series.get("theme_keywords") or [] if kw.lower() in text_lower)


def stamp_script_series(script: dict, episode_index: int, series: dict | None = None) -> dict:
    series = series or get_active_series()
    if not series:
        script.setdefault("series_note", None)
        return script

    target = int(series.get("episode_count_target") or 0)
    title = series.get("title") or series.get("id")
    ep = episode_index
    note = f"{title} · Ep {ep}/{target}" if target else f"{title} · Ep {ep}"
    script["series_id"] = series.get("id")
    script["series_title"] = title
    script["episode_index"] = ep
    script["series_note"] = note
    return script


def increment_episodes_completed(count: int = 1) -> None:
    data = load_calendar()
    active_id = data.get("active_series_id")
    for s in data.get("series") or []:
        if s.get("id") == active_id:
            s["episodes_completed"] = int(s.get("episodes_completed") or 0) + count
            break
    save_calendar(data)


def mashup_watchlist() -> list[str]:
    return list(load_calendar().get("mashup_watchlist") or [])


def filter_topics_for_series(
    topics: list[dict],
    *,
    max_off_arc: int = 1,
    series: dict | None = None,
) -> list[dict]:
    """Prefer on-arc topics; allow a small off-arc budget."""
    series = series or get_active_series()
    if not series:
        return topics

    on_arc: list[dict] = []
    off_arc: list[dict] = []
    for t in topics:
        blob = f"{t.get('topic_title', '')} {t.get('topic_summary', '')}"
        if series_keyword_boost(blob, series) > 0:
            on_arc.append(t)
        else:
            off_arc.append(t)

    return on_arc + off_arc[:max_off_arc]

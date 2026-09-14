from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

_root = Path(__file__).resolve().parent
load_dotenv(_root / ".env")
load_dotenv(_root.parent / ".env")

from src.research import fetch_topics
from src.safety_filter import filter_topics
from src.journal_enrich import enrich_journal_topics
from src.matcher import (
    count_pending_queue,
    mark_queue_consumed,
    pull_queue_entries,
    score_topics,
    _load_journal_config,
)
from src.generator import generate_scripts
from src.deliver import send_via_telegram
from src.content_phase import get_phase, get_phase_label
from src.series_calendar import filter_topics_for_series, get_active_series


def _select_growth_topics(scored_topics: list[dict], count: int = 8, news_slots: int = 3) -> list[dict]:
    """Prefer calendar/manual seeds, then series-aligned timely/fresh pool.

    Target seed split for an 8-pack (journal filled upstream): calendar first,
    then ~timely news, rest evergreen. Outlier soft-pads from fresh for now.
    """
    series = get_active_series()
    calendar_pre = [
        t for t in scored_topics
        if t.get("seed_origin") == "calendar" or t.get("source_platform") == "hook_bank"
        or t.get("estimated_virality") == "manual"
    ]
    calendar_titles_pre = {t["topic_title"] for t in calendar_pre}
    non_calendar = [t for t in scored_topics if t["topic_title"] not in calendar_titles_pre]
    if series:
        print(f"📚 Series: {series.get('title')} — filtering topics to arc (calendar exempt)")
        non_calendar = filter_topics_for_series(non_calendar, max_off_arc=2, series=series)
    scored_topics = calendar_pre + non_calendar

    calendar = [
        t for t in scored_topics
        if t.get("seed_origin") == "calendar" or t.get("source_platform") == "hook_bank"
        or t.get("estimated_virality") == "manual"
    ]
    # Prefer structured calendar over plain manual override
    calendar.sort(
        key=lambda t: (
            0 if t.get("seed_origin") == "calendar" else 1,
            -float(t.get("engagement_score") or 0),
            -t.get("match_score", 0),
        )
    )
    for t in calendar:
        t.setdefault("seed_origin", "calendar" if t.get("hook_bank_id") else "manual")

    calendar_titles = {t["topic_title"] for t in calendar}
    remaining = [t for t in scored_topics if t["topic_title"] not in calendar_titles]

    def _timely_key(t: dict) -> tuple:
        platform = (t.get("source_platform") or "").lower()
        tldr_boost = 0 if platform == "tldr" else 1
        return (
            tldr_boost,
            {"hack": 0, "social": 1, "story": 2, "news": 3}.get(t.get("source_type", "trend"), 4),
            -t.get("match_score", 0),
            -float(t.get("engagement_score") or 0),
        )

    timely_pool = sorted(
        [t for t in remaining if t.get("source_type") in ("story", "news", "social", "hack")],
        key=_timely_key,
    )[: max(0, news_slots)]
    for t in timely_pool:
        t.setdefault("seed_origin", "fresh")

    timely_titles = {t["topic_title"] for t in timely_pool}
    evergreen = sorted(
        [t for t in remaining if t["topic_title"] not in timely_titles],
        key=lambda t: (t.get("match_score", 0), float(t.get("engagement_score") or 0)),
        reverse=True,
    )
    for t in evergreen:
        if t.get("seed_origin") == "outlier":
            continue
        t.setdefault("seed_origin", "fresh")

    # Calendar fills first (up to count), then timely, then evergreen
    batch: list[dict] = []
    for pool in (calendar, timely_pool, evergreen):
        for t in pool:
            if len(batch) >= count:
                break
            if t["topic_title"] in {b["topic_title"] for b in batch}:
                continue
            batch.append(t)
        if len(batch) >= count:
            break

    selected = batch[:count]
    cal_n = sum(1 for t in selected if t.get("seed_origin") == "calendar")
    if cal_n:
        print(f"   Seed split: {cal_n} calendar + {len(selected) - cal_n} other")
    outlier_n = sum(1 for t in selected if t.get("seed_origin") == "outlier")
    if outlier_n < 2 and cal_n == 0:
        print(f"   Seed split: outlier soft-miss ({outlier_n}/2) — padding from fresh")
    return selected


def _stamp_seed_origins(journal_topics: list[dict], trending_batch: list[dict]) -> None:
    for t in journal_topics:
        t["seed_origin"] = "journal"
    for t in trending_batch:
        t.setdefault("seed_origin", "fresh")


def _batch_size_for_phase(phase: str) -> int:
    config = _load_journal_config()
    if phase == "intro":
        return int(config.get("intro_batch_size", 4))
    return int(config.get("max_batch_size", 8))


def _journal_slots_for_batch(phase: str, max_batch: int) -> int:
    """How many personal journal topics to pull — up to pending queue or batch cap."""
    pending = count_pending_queue()
    if pending <= 0:
        return 0
    return min(pending, max_batch)


def _news_slots_for_batch(journal_count: int, remaining: int, phase: str) -> int:
    if phase != "growth" or remaining <= 0:
        return 0
    config = _load_journal_config()
    skip_at = int(config.get("skip_news_when_journal_at_least", 3))
    if journal_count >= skip_at:
        return 0
    return min(3, remaining)


async def _build_trending_batch(
    remaining: int,
    phase: str,
    news_slots: int | None = None,
) -> tuple[list[dict], list[dict], int]:
    """Fetch, filter, and score trending topics. Returns (batch, raw_topics, dropped)."""
    if remaining <= 0:
        return [], [], 0

    if news_slots is None:
        news_slots = min(3, remaining) if phase == "growth" else 0

    print("📡 Fetching trending topics...")
    raw_topics = await fetch_topics()
    print(f"   Found {len(raw_topics)} raw topics")

    print("🛡️ Applying safety filter...")
    safe_topics = await filter_topics(raw_topics)
    dropped = len(raw_topics) - len(safe_topics)
    print(f"   {len(safe_topics)} safe topics ({dropped} dropped)")

    print("🎯 Matching to knowledge base...")
    scored_topics = score_topics(safe_topics)

    if phase == "intro":
        manual = [t for t in scored_topics if t.get("estimated_virality") == "manual"]
        topic_pool = manual if manual else scored_topics
        trending_batch = topic_pool[:remaining]
    else:
        trending_batch = _select_growth_topics(
            scored_topics, count=remaining, news_slots=news_slots,
        )

    return trending_batch, raw_topics, dropped


async def main():
    print(f"🚀 Script Engine starting — {datetime.now()}")
    phase = get_phase()
    print(f"📍 Content phase: {get_phase_label()}")

    total_slots = _batch_size_for_phase(phase)
    journal_slots = _journal_slots_for_batch(phase, total_slots)
    journal_topics = pull_queue_entries(journal_slots)
    remaining = total_slots - len(journal_topics)

    if journal_topics:
        print(f"📓 Journal queue: {len(journal_topics)} personal topic(s) ({count_pending_queue()} pending)")
    else:
        print("📓 Journal queue empty — all slots from community research")

    raw_topics: list[dict] = []
    dropped = 0
    trending_batch: list[dict] = []

    if journal_topics:
        print("🛡️ Applying safety filter to journal topics...")
        safe_journal = await filter_topics(journal_topics)
        journal_dropped = len(journal_topics) - len(safe_journal)
        dropped += journal_dropped
        journal_topics = safe_journal
        remaining = total_slots - len(journal_topics)
        if journal_dropped:
            print(f"   {journal_dropped} journal topic(s) dropped by safety filter")

    news_slots = _news_slots_for_batch(len(journal_topics), remaining, phase)
    if journal_topics and remaining > 0:
        journal_topics, (trending_batch, raw_topics, trend_dropped) = await asyncio.gather(
            enrich_journal_topics(journal_topics),
            _build_trending_batch(remaining, phase, news_slots=news_slots),
        )
        dropped += trend_dropped
    elif journal_topics:
        journal_topics = await enrich_journal_topics(journal_topics)
        if remaining <= 0:
            print("📓 Personal queue filled all slots — skipping community research")
    elif remaining > 0:
        trending_batch, raw_topics, trend_dropped = await _build_trending_batch(
            remaining, phase, news_slots=news_slots,
        )
        dropped += trend_dropped

    combined = journal_topics + trending_batch
    _stamp_seed_origins(journal_topics, trending_batch)
    topics_researched = len(raw_topics) + len(journal_topics)

    print("✍️ Generating scripts...")
    if phase == "growth" and (journal_topics or trending_batch):
        news_count = sum(1 for t in trending_batch if t.get("source_type") == "news")
        story_count = sum(1 for t in trending_batch if t.get("source_type") == "story")
        evergreen_count = len(trending_batch) - news_count - story_count
        origin_counts: dict[str, int] = {}
        for t in combined:
            origin_counts[t.get("seed_origin") or "fresh"] = origin_counts.get(
                t.get("seed_origin") or "fresh", 0
            ) + 1
        print(
            f"   Batch mix: {len(journal_topics)} journal + {story_count} story + "
            f"{news_count} news + {evergreen_count} evergreen"
        )
        print(f"   Seed origins: {origin_counts}")
    scripts = await generate_scripts(combined, phase=phase)
    print(f"   Generated {len(scripts)} scripts")

    if journal_topics and scripts:
        mark_queue_consumed(journal_topics, scripts)

    print("📱 Sending to Telegram...")
    await send_via_telegram(
        scripts=scripts,
        topics_researched=topics_researched,
        topics_dropped=dropped,
        content_phase=phase,
    )

    try:
        from src.hook_bank import mark_scripted_from_scripts

        marked = mark_scripted_from_scripts(scripts)
        if marked:
            print(f"📅 Hook bank: marked {marked} calendar hook(s) scripted")
    except Exception as exc:
        print(f"⚠️ Hook bank status update skipped: {exc}")

    print("✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())

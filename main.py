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


def _select_growth_topics(scored_topics: list[dict], count: int = 8, news_slots: int = 3) -> list[dict]:
    """Reserve timely slots (story preferred over news); fill rest with highest-scored evergreen."""
    timely_pool = sorted(
        [t for t in scored_topics if t.get("source_type") in ("story", "news", "social")],
        key=lambda t: (
            {"story": 0, "social": 1, "news": 2}.get(t.get("source_type", "trend"), 3),
            -t.get("match_score", 0),
        ),
    )[:news_slots]
    timely_titles = {t["topic_title"] for t in timely_pool}
    evergreen = sorted(
        [t for t in scored_topics if t["topic_title"] not in timely_titles],
        key=lambda t: t.get("match_score", 0),
        reverse=True,
    )
    batch = timely_pool + evergreen
    return batch[:count]


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
        print("📓 Journal queue empty — all slots from Perplexity")

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
            print("📓 Personal queue filled all slots — skipping Perplexity")
    elif remaining > 0:
        trending_batch, raw_topics, trend_dropped = await _build_trending_batch(
            remaining, phase, news_slots=news_slots,
        )
        dropped += trend_dropped

    combined = journal_topics + trending_batch
    topics_researched = len(raw_topics) + len(journal_topics)

    print("✍️ Generating scripts...")
    if phase == "growth" and (journal_topics or trending_batch):
        news_count = sum(1 for t in trending_batch if t.get("source_type") == "news")
        story_count = sum(1 for t in trending_batch if t.get("source_type") == "story")
        evergreen_count = len(trending_batch) - news_count - story_count
        print(
            f"   Batch mix: {len(journal_topics)} journal + {story_count} story + "
            f"{news_count} news + {evergreen_count} evergreen"
        )
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

    print("✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

_root = Path(__file__).resolve().parent
load_dotenv(_root / ".env")
load_dotenv(_root.parent / ".env")

from src.research import fetch_topics
from src.safety_filter import filter_topics
from src.matcher import (
    mark_queue_consumed,
    pull_queue_entries,
    score_topics,
    _load_journal_config,
)
from src.generator import generate_scripts
from src.deliver import send_via_telegram
from src.content_phase import get_phase, get_phase_label


def _select_growth_topics(scored_topics: list[dict], count: int = 8, news_slots: int = 3) -> list[dict]:
    """Reserve slots for timely news topics; fill rest with highest-scored evergreen."""
    news = sorted(
        [t for t in scored_topics if t.get("source_type") == "news"],
        key=lambda t: t.get("match_score", 0),
        reverse=True,
    )[:news_slots]
    news_titles = {t["topic_title"] for t in news}
    evergreen = sorted(
        [t for t in scored_topics if t["topic_title"] not in news_titles],
        key=lambda t: t.get("match_score", 0),
        reverse=True,
    )
    batch = news + evergreen
    return batch[:count]


def _reserved_journal_slots(phase: str) -> int:
    config = _load_journal_config()
    slots = config.get("reserved_slots", {"intro": 1, "growth": 3})
    return int(slots.get(phase, 1 if phase == "intro" else 3))


async def main():
    print(f"🚀 Script Engine starting — {datetime.now()}")
    phase = get_phase()
    print(f"📍 Content phase: {get_phase_label()}")

    total_slots = 4 if phase == "intro" else 8
    reserved = _reserved_journal_slots(phase)
    journal_topics = pull_queue_entries(reserved)
    remaining = total_slots - len(journal_topics)

    if journal_topics:
        print(f"📓 Journal queue: {len(journal_topics)} priority slot(s) filled")
    else:
        print("📓 Journal queue empty — all slots from Perplexity")

    raw_topics: list[dict] = []
    safe_topics: list[dict] = []
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

    if remaining > 0:
        print("📡 Fetching trending topics...")
        raw_topics = await fetch_topics()
        print(f"   Found {len(raw_topics)} raw topics")

        print("🛡️ Applying safety filter...")
        safe_topics = await filter_topics(raw_topics)
        perplexity_dropped = len(raw_topics) - len(safe_topics)
        dropped += perplexity_dropped
        print(f"   {len(safe_topics)} safe topics ({perplexity_dropped} dropped)")

        print("🎯 Matching to knowledge base...")
        scored_topics = score_topics(safe_topics)

        if phase == "intro":
            manual = [t for t in scored_topics if t.get("estimated_virality") == "manual"]
            topic_pool = manual if manual else scored_topics
            trending_batch = topic_pool[:remaining]
        else:
            trending_batch = _select_growth_topics(scored_topics, count=remaining, news_slots=min(3, remaining))

    combined = journal_topics + trending_batch
    topics_researched = len(raw_topics) + len(journal_topics)

    print("✍️ Generating scripts...")
    if phase == "growth" and trending_batch:
        news_count = sum(1 for t in trending_batch if t.get("source_type") == "news")
        print(f"   Batch mix: {len(journal_topics)} journal + {news_count} news + {len(trending_batch) - news_count} evergreen")
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

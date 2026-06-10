import asyncio
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env from script-engine/ or parent CretorAuto/ directory
_root = Path(__file__).resolve().parent
load_dotenv(_root / ".env")
load_dotenv(_root.parent / ".env")

from src.research import fetch_topics
from src.safety_filter import filter_topics
from src.matcher import score_topics
from src.generator import generate_scripts
from src.deliver import send_via_telegram
from src.content_phase import get_phase, get_phase_label


async def main():
    print(f"🚀 Script Engine starting — {datetime.now()}")
    phase = get_phase()
    print(f"📍 Content phase: {get_phase_label()}")

    # Step 1: Research
    print("📡 Fetching trending topics...")
    raw_topics = await fetch_topics()
    print(f"   Found {len(raw_topics)} raw topics")

    # Step 2: Safety filter
    print("🛡️ Applying safety filter...")
    safe_topics = await filter_topics(raw_topics)
    dropped = len(raw_topics) - len(safe_topics)
    print(f"   {len(safe_topics)} safe topics ({dropped} dropped)")

    # Step 3: Match against knowledge base
    print("🎯 Matching to knowledge base...")
    scored_topics = score_topics(safe_topics)

    # Step 4: Generate scripts (intro = 4 brand scripts, growth = top 8)
    print("✍️ Generating scripts...")
    if phase == "intro":
        manual = [t for t in scored_topics if t.get("estimated_virality") == "manual"]
        topic_pool = manual if manual else scored_topics
        scripts = await generate_scripts(topic_pool[:4], phase="intro")
    else:
        scripts = await generate_scripts(scored_topics[:8], phase="growth")
    print(f"   Generated {len(scripts)} scripts")

    # Step 5: Deliver
    print("📱 Sending to Telegram...")
    await send_via_telegram(
        scripts=scripts,
        topics_researched=len(raw_topics),
        topics_dropped=dropped,
        content_phase=phase,
    )

    print("✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())

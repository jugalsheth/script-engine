import json
import os
import re
from pathlib import Path

import anthropic

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
HAIKU_MODEL = "claude-haiku-4-5-20251001"


def _load_blocklist() -> list[str]:
    blocklist_path = CONFIG_DIR / "blocklist.txt"
    try:
        lines = blocklist_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"⚠️ Could not read blocklist.txt: {exc}")
        return []
    return [line.strip().lower() for line in lines if line.strip()]


def _blocklist_filter(topics: list[dict], blocklist: list[str]) -> tuple[list[dict], int]:
    safe: list[dict] = []
    dropped = 0

    for topic in topics:
        haystack = f"{topic.get('topic_title', '')} {topic.get('topic_summary', '')}".lower()
        if any(term in haystack for term in blocklist):
            dropped += 1
            continue
        safe.append(topic)

    return safe, dropped


def _parse_haiku_safety_response(content: str) -> list[dict]:
    json_match = re.search(r"\[[\s\S]*\]", content)
    if not json_match:
        return []
    try:
        parsed = json.loads(json_match.group())
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return []


async def _ai_safety_check(topics: list[dict]) -> tuple[list[dict], int]:
    """Layer 2 — Claude Haiku batch safety check. Fails silently."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or not topics:
        return topics, 0

    topic_payload = [
        {
            "topic_title": t["topic_title"],
            "topic_summary": t.get("topic_summary", ""),
        }
        for t in topics
    ]

    prompt = (
        "For each topic below, return a JSON array of "
        '{topic_title, safe: bool}. Safe means: no political content, '
        "no government criticism, no divisive social commentary, "
        "nothing that could be misread as anti-American or "
        "controversial for a professional creator on a work visa. "
        "When in doubt, safe = false.\n\n"
        f"Topics:\n{json.dumps(topic_payload, indent=2)}\n\n"
        'Return ONLY a JSON array: [{"topic_title": "...", "safe": true/false}]'
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text
        safety_results = _parse_haiku_safety_response(content)

        unsafe_titles = {
            item["topic_title"].lower().strip()
            for item in safety_results
            if isinstance(item, dict) and item.get("safe") is False
        }

        if not unsafe_titles:
            return topics, 0

        filtered = [
            t for t in topics if t["topic_title"].lower().strip() not in unsafe_titles
        ]
        return filtered, len(topics) - len(filtered)

    except Exception:
        return topics, 0


async def filter_topics(topics: list[dict]) -> list[dict]:
    """Apply blocklist (layer 1) and AI safety (layer 2) filters."""
    blocklist = _load_blocklist()
    blocklist_safe, layer1_dropped = _blocklist_filter(topics, blocklist)
    print(f"   Layer 1 (blocklist): dropped {layer1_dropped} topic(s)")

    ai_safe, layer2_dropped = await _ai_safety_check(blocklist_safe)
    print(f"   Layer 2 (AI): dropped {layer2_dropped} topic(s)")

    return ai_safe

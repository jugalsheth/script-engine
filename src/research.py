from __future__ import annotations

import json
import os
import re
from pathlib import Path

import httpx

from src.community_research import fetch_community_topics
from src.series_calendar import filter_topics_for_series, get_active_series

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar"
PERPLEXITY_MAX_TOKENS = 1200
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# Perplexity only enriches real community URLs — does not invent the topic list.
ENRICH_PROMPT = """You enrich story seeds for a vibe-coding / AI coding tools creator
(Cursor, Claude Code, tokens, MCP, shipping hacks).

Given these real community threads (title + url + summary), return a JSON array with the
SAME count of objects. For each:
- topic_title (punchy, actionable — keep close to original)
- topic_summary (2 sentences — tension + why builders care)
- story_hook (one opening line with a named tool)
- protagonist, tension, payoff
- source_type: hack | tip | build | news | confession | social
- estimated_virality: high | medium | low
- keep source_url exactly as provided

Return ONLY a JSON array. No markdown.

THREADS:
{threads}
"""

SOURCE_TYPES = [
    "news",
    "social",
    "trend",
    "story",
    "hack",
    "tip",
    "build",
    "confession",
]

FALLBACK_TOPICS = [
    {
        "topic_title": "Claude Code + Higgsfield: generate the visual while the agent writes code",
        "topic_summary": "Wire Higgsfield MCP into Claude Code so the agent can spit a product render while it ships the page. One mashup, visible proof.",
        "source_type": "hack",
        "estimated_virality": "high",
        "format_hint": "hack",
    },
    {
        "topic_title": "The Cursor setting that stops silent token overspend",
        "topic_summary": "Most builders never check usage until the bill hits. One dashboard habit and model routing rule cuts waste without killing flow.",
        "source_type": "tip",
        "estimated_virality": "high",
        "format_hint": "tip",
    },
    {
        "topic_title": "CLAUDE.md rules that make Claude Code ship instead of wander",
        "topic_summary": "Vague CLAUDE.md files create agent thrash. Tight plan-then-execute rules plus a done definition change output quality.",
        "source_type": "tip",
        "estimated_virality": "high",
        "format_hint": "tip",
    },
    {
        "topic_title": "Plan in Claude, ship in Cursor — the split that actually works",
        "topic_summary": "Using one tool for everything blurs thinking and shipping. Separating plan vs execute is the builder stack that sticks.",
        "source_type": "hack",
        "estimated_virality": "high",
        "format_hint": "hack",
    },
    {
        "topic_title": "I vibe coded for three hours and shipped nothing",
        "topic_summary": "Demo theater feels productive until you check git. One constraint — ship a vertical slice in 60 minutes — fixes it.",
        "source_type": "confession",
        "estimated_virality": "high",
        "format_hint": "confession",
    },
    {
        "topic_title": "One MCP every Cursor power user should add this week",
        "topic_summary": "MCP turns the IDE into a tool router. Pick one connector that removes a daily copy-paste and wire it once.",
        "source_type": "hack",
        "estimated_virality": "medium",
        "format_hint": "hack",
    },
    {
        "topic_title": "When to use Sonnet vs Opus so you stop burning tokens",
        "topic_summary": "Frontier models for ambiguous architecture; cheaper models for mechanical edits. Matching ammo to mission is token economics.",
        "source_type": "tip",
        "estimated_virality": "high",
        "format_hint": "tip",
    },
    {
        "topic_title": "Cursor agent mode vs Claude Code — when each wins",
        "topic_summary": "Honest tradeoffs: IDE-native agents vs terminal agents. Pick by task shape, not hype.",
        "source_type": "tip",
        "estimated_virality": "high",
        "format_hint": "tip",
    },
    {
        "topic_title": "Ship a landing page with Claude Code in one sitting",
        "topic_summary": "Micro-build: scoped prompt, CLAUDE.md constraints, and a definition of done that includes deploy.",
        "source_type": "build",
        "estimated_virality": "medium",
        "format_hint": "build",
    },
    {
        "topic_title": "The changelog tip: turn a Cursor update into a Reel the same day",
        "topic_summary": "Actionable news — read the release note, try one feature, film the receipt. Freshness beats evergreen listicles.",
        "source_type": "news",
        "estimated_virality": "medium",
        "format_hint": "news",
    },
    {
        "topic_title": "Stop pasting screenshots — use browser MCP from the agent",
        "topic_summary": "Agents that can see the page debug faster. One MCP setup removes the screenshot loop.",
        "source_type": "hack",
        "estimated_virality": "medium",
        "format_hint": "hack",
    },
    {
        "topic_title": "Rules files that keep multi-file agents from rewriting your app",
        "topic_summary": "Unscoped agents refactor everything. Boundary rules and allowlists keep vibe coding from becoming chaos.",
        "source_type": "tip",
        "estimated_virality": "medium",
        "format_hint": "tip",
    },
    {
        "topic_title": "How I review Claude Code diffs before I merge",
        "topic_summary": "Trust but verify — a three-pass review habit catches confident wrong code before it ships.",
        "source_type": "tip",
        "estimated_virality": "medium",
        "format_hint": "tip",
    },
    {
        "topic_title": "Build a skill once — reuse it every session",
        "topic_summary": "Skills beat re-prompting. Package a repeatable workflow so every session starts smarter.",
        "source_type": "hack",
        "estimated_virality": "high",
        "format_hint": "hack",
    },
    {
        "topic_title": "Vibe coding theater vs shipping — the 60-minute rule",
        "topic_summary": "If there is no runnable demo in an hour, you were exploring, not building. Constraint creates shipping.",
        "source_type": "confession",
        "estimated_virality": "high",
        "format_hint": "confession",
    },
]

VIRALITY_ORDER = {"high": 0, "medium": 1, "low": 2, "manual": 3}


def _load_manual_topics() -> list[dict]:
    """Prefer active calendar week seeds; fall back to topics_override.txt lines."""
    try:
        from src.hook_bank import active_week, topics_for_week

        cal_topics = topics_for_week(active_week())
        if cal_topics:
            print(f"   Calendar seeds: {len(cal_topics)} from week {active_week()}")
            return cal_topics
    except Exception as exc:
        print(f"⚠️ Hook bank calendar unavailable: {exc}")

    override_path = CONFIG_DIR / "topics_override.txt"
    manual_topics = []

    try:
        lines = override_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"⚠️ Could not read topics_override.txt: {exc}")
        return manual_topics

    skip_prefixes = ("add specific", "leave empty", "example:", "#")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.lower().startswith(prefix) for prefix in skip_prefixes):
            continue
        manual_topics.append(
            {
                "topic_title": stripped,
                "topic_summary": f"Manual topic requested by creator: {stripped}",
                "source_type": "hack",
                "estimated_virality": "manual",
                "format_hint": "hack",
                "seed_origin": "manual",
                "source_platform": "topics_override",
            }
        )

    return manual_topics


def _normalize_topic(raw: dict, default_source: str) -> dict | None:
    title = (raw.get("topic_title") or raw.get("title") or "").strip()
    summary = (raw.get("topic_summary") or raw.get("summary") or "").strip()

    if not title:
        return None

    if not summary:
        summary = f"Builder discussion around {title} in AI coding tools communities."

    source_type = (raw.get("source_type") or default_source).lower()
    if source_type not in SOURCE_TYPES:
        source_type = default_source

    virality = (raw.get("estimated_virality") or "medium").lower()
    if virality not in ("high", "medium", "low", "manual"):
        virality = "medium"

    topic = {
        "topic_title": title,
        "topic_summary": summary,
        "source_type": source_type,
        "estimated_virality": virality,
        "story_hook": (raw.get("story_hook") or "").strip(),
        "protagonist": (raw.get("protagonist") or "").strip(),
        "tension": (raw.get("tension") or "").strip(),
        "payoff": (raw.get("payoff") or "").strip(),
        "source_url": (raw.get("source_url") or "").strip(),
        "source_platform": (raw.get("source_platform") or "").strip(),
        "engagement_score": float(raw.get("engagement_score") or 0),
        "format_hint": (raw.get("format_hint") or source_type or "hack").strip(),
    }
    for key in (
        "seed_origin",
        "hook_bank_id",
        "series_arc",
        "pillar",
        "adaptation_note",
        "calendar_week",
        "calendar_slot",
        "script_type_hint",
    ):
        if raw.get(key) is not None:
            topic[key] = raw[key]
    return topic


def _parse_topics_from_response(content: str, source_type: str) -> list[dict]:
    topics: list[dict] = []

    json_match = re.search(r"\[[\s\S]*\]", content)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        normalized = _normalize_topic(item, source_type)
                        if normalized:
                            topics.append(normalized)
                if topics:
                    return topics
        except json.JSONDecodeError:
            pass

    return topics


def _dedupe_topics(topics: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for topic in topics:
        key = topic["topic_title"].lower().strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(topic)
    return unique


def _ensure_topic_count(topics: list[dict]) -> list[dict]:
    topics = _dedupe_topics(topics)

    if len(topics) < 15:
        for fallback in FALLBACK_TOPICS:
            if len(topics) >= 15:
                break
            title_key = fallback["topic_title"].lower()
            if not any(t["topic_title"].lower() == title_key for t in topics):
                topics.append(dict(fallback))

    topics.sort(
        key=lambda t: (
            VIRALITY_ORDER.get(t.get("estimated_virality", "low"), 2),
            -float(t.get("engagement_score") or 0),
        )
    )
    return topics[:30]


def _log_perplexity_cost(data: dict) -> None:
    usage = data.get("usage", {})
    cost = usage.get("cost", {})
    total = cost.get("total_cost")
    if total is not None:
        print(f"   Perplexity enrich cost: ${total:.4f}")


async def _enrich_with_perplexity(
    client: httpx.AsyncClient,
    api_key: str,
    seeds: list[dict],
) -> list[dict]:
    """Optional enrich of top community seeds — never invents the list."""
    top = [s for s in seeds if s.get("source_url")][:8]
    if not top:
        return seeds

    thread_lines = []
    for s in top:
        thread_lines.append(
            f"- title: {s['topic_title']}\n  url: {s.get('source_url')}\n  "
            f"summary: {s.get('topic_summary', '')[:200]}"
        )
    prompt = ENRICH_PROMPT.format(threads="\n".join(thread_lines))
    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": PERPLEXITY_MAX_TOKENS,
        "web_search_options": {"search_context_size": "low"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = await client.post(
        PERPLEXITY_API_URL, json=payload, headers=headers, timeout=90.0
    )
    response.raise_for_status()
    data = response.json()
    _log_perplexity_cost(data)
    content = data["choices"][0]["message"]["content"]
    enriched = _parse_topics_from_response(content, "social")
    if not enriched:
        return seeds

    # Merge enrich fields back onto originals by URL or title
    by_url = {e.get("source_url"): e for e in enriched if e.get("source_url")}
    by_title = {e["topic_title"].lower(): e for e in enriched}
    merged: list[dict] = []
    for s in seeds:
        e = by_url.get(s.get("source_url")) or by_title.get(s["topic_title"].lower())
        if e:
            out = dict(s)
            for key in (
                "topic_title",
                "topic_summary",
                "story_hook",
                "protagonist",
                "tension",
                "payoff",
                "source_type",
                "estimated_virality",
            ):
                if e.get(key):
                    out[key] = e[key]
            merged.append(out)
        else:
            merged.append(s)
    return merged


async def fetch_topics() -> list[dict]:
    """Fetch topics from community signals; optionally enrich with Perplexity."""
    manual_topics = _load_manual_topics()
    series = get_active_series()
    if series:
        print(f"   Active series: {series.get('title')} ({series.get('id')})")

    community: list[dict] = []
    try:
        community = await fetch_community_topics()
    except Exception as exc:
        print(f"⚠️ Community research failed: {exc}")

    api_key = os.getenv("PERPLEXITY_API_KEY")
    skip_perplexity = os.getenv("PERPLEXITY_SKIP", "").lower() in ("1", "true", "yes")

    if community and api_key and not skip_perplexity:
        try:
            async with httpx.AsyncClient() as client:
                community = await _enrich_with_perplexity(client, api_key, community)
        except Exception as exc:
            print(f"⚠️ Perplexity enrich failed (using raw community seeds): {exc}")
    elif not api_key:
        print("   PERPLEXITY_API_KEY not set — community seeds only (no enrich)")
    elif skip_perplexity:
        print("   PERPLEXITY_SKIP — community seeds only")

    combined = manual_topics + community
    if len(combined) < 10:
        print("   Padding with vibe-coding fallback topics")
        combined = combined + list(FALLBACK_TOPICS)

    # Keep calendar/manual seeds even if off the active series arc
    protected = [
        t for t in combined
        if t.get("seed_origin") in ("calendar", "manual")
        or t.get("source_platform") in ("hook_bank", "topics_override")
        or t.get("estimated_virality") == "manual"
    ]
    protected_titles = {t["topic_title"] for t in protected}
    others = [t for t in combined if t["topic_title"] not in protected_titles]
    others = filter_topics_for_series(others, max_off_arc=5)
    combined = protected + others
    final = _ensure_topic_count(combined)
    print(f"   Research complete: {len(final)} topics (community-first, calendar-protected)")
    return final

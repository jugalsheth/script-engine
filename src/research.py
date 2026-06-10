from __future__ import annotations

import json
import os
import re
from pathlib import Path

import httpx

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar"
# One batched query replaces 5 parallel calls — search fee is per request, not per topic.
PERPLEXITY_MAX_TOKENS = 2000
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

BATCHED_RESEARCH_PROMPT = """Research trending video topics for a senior AI/data engineer creating
60-90 second Instagram Reels and LinkedIn videos. Cover ALL of these angles in one pass:

1. Trending tech career advice this week
2. What software engineers discuss on Reddit/social this week
3. Viral tech content on Instagram, LinkedIn, YouTube
4. Job market stats for data engineering and AI engineering
5. Skills hiring managers want in tech right now

Return exactly 20 distinct topic ideas as a JSON array. Each object must have:
- topic_title (string)
- topic_summary (2-3 sentences)
- source_type ("news", "social", or "trend")
- estimated_virality ("high", "medium", or "low")

Return ONLY valid JSON array, no markdown."""

SOURCE_TYPES = ["news", "social", "trend"]

FALLBACK_TOPICS = [
    {
        "topic_title": "How to stand out in a data engineering interview",
        "topic_summary": "Hiring managers see hundreds of similar resumes. Specific portfolio projects and pipeline stories differentiate candidates in a crowded market.",
        "source_type": "trend",
        "estimated_virality": "medium",
    },
    {
        "topic_title": "Three SQL patterns every engineer should know",
        "topic_summary": "Window functions, CTEs, and proper indexing solve 80% of real-world query problems. Most bootcamps skip the patterns that matter in production.",
        "source_type": "trend",
        "estimated_virality": "medium",
    },
    {
        "topic_title": "What I wish I knew before my first AWS deployment",
        "topic_summary": "IAM permissions, cost alerts, and rollback plans prevent the painful lessons most engineers learn the hard way on their first cloud project.",
        "source_type": "trend",
        "estimated_virality": "medium",
    },
    {
        "topic_title": "How to learn a new tech stack in 30 days",
        "topic_summary": "Structured project-based learning beats tutorial hell. A single end-to-end build teaches more than weeks of passive video watching.",
        "source_type": "trend",
        "estimated_virality": "high",
    },
    {
        "topic_title": "The real difference between junior and senior engineers",
        "topic_summary": "Senior engineers optimize for clarity, tradeoffs, and maintainability — not just getting code to work. The gap is decision-making, not syntax.",
        "source_type": "trend",
        "estimated_virality": "high",
    },
    {
        "topic_title": "Why your LinkedIn profile is not getting recruiter views",
        "topic_summary": "Most engineers list tools instead of outcomes. Recruiters search for impact keywords and project results, not a laundry list of technologies.",
        "source_type": "trend",
        "estimated_virality": "high",
    },
    {
        "topic_title": "The one habit that makes you a faster debugger",
        "topic_summary": "Reproducing the bug in isolation before touching production code saves hours. Most engineers skip this step and chase symptoms instead.",
        "source_type": "trend",
        "estimated_virality": "medium",
    },
    {
        "topic_title": "How to explain ETL to a non-technical stakeholder",
        "topic_summary": "Business leaders do not care about pipelines — they care about timely reports. Framing data movement as business outcomes unlocks budget and buy-in.",
        "source_type": "trend",
        "estimated_virality": "medium",
    },
    {
        "topic_title": "What hiring managers actually look for in AI engineers",
        "topic_summary": "Beyond model buzzwords, teams need people who can ship reliable systems — evaluation, monitoring, and integration matter more than notebook demos.",
        "source_type": "trend",
        "estimated_virality": "high",
    },
    {
        "topic_title": "How to prioritize learning when everything feels urgent",
        "topic_summary": "Skill stacking beats chasing every new framework. Pick one high-leverage skill per quarter and build a project that proves you can use it.",
        "source_type": "trend",
        "estimated_virality": "medium",
    },
    {
        "topic_title": "The hidden cost of over-engineering your side project",
        "topic_summary": "Perfect architecture on a project nobody uses is wasted effort. Ship a minimal version first, then refactor based on real feedback.",
        "source_type": "trend",
        "estimated_virality": "medium",
    },
    {
        "topic_title": "How to write a README that gets you hired",
        "topic_summary": "Recruiters and hiring managers click through to GitHub. A clear README with setup steps, architecture diagram, and results tells a story resumes cannot.",
        "source_type": "trend",
        "estimated_virality": "medium",
    },
    {
        "topic_title": "Why batch jobs fail at 2am and how to prevent it",
        "topic_summary": "Silent data quality issues, memory limits, and missing alerts cause most overnight pipeline failures. Proactive monitoring beats reactive firefighting.",
        "source_type": "trend",
        "estimated_virality": "low",
    },
    {
        "topic_title": "How to use Claude for real engineering work",
        "topic_summary": "LLMs accelerate boilerplate and documentation but need guardrails. Pair AI output with tests and code review — never ship unverified generated code.",
        "source_type": "trend",
        "estimated_virality": "high",
    },
    {
        "topic_title": "Three questions to ask before accepting a tech job offer",
        "topic_summary": "Team structure, on-call expectations, and growth path matter as much as base salary. Clarity upfront prevents regret six months in.",
        "source_type": "trend",
        "estimated_virality": "high",
    },
]

VIRALITY_ORDER = {"high": 0, "medium": 1, "low": 2, "manual": 3}


def _load_manual_topics() -> list[dict]:
    """Read non-comment, non-empty lines from topics_override.txt."""
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
                "source_type": "trend",
                "estimated_virality": "manual",
            }
        )

    return manual_topics


def _normalize_topic(raw: dict, default_source: str) -> dict | None:
    title = (raw.get("topic_title") or raw.get("title") or "").strip()
    summary = (raw.get("topic_summary") or raw.get("summary") or "").strip()

    if not title:
        return None

    if not summary:
        summary = f"Trending discussion around {title} in tech and career communities."

    source_type = (raw.get("source_type") or default_source).lower()
    if source_type not in SOURCE_TYPES:
        source_type = default_source

    virality = (raw.get("estimated_virality") or "medium").lower()
    if virality not in ("high", "medium", "low", "manual"):
        virality = "medium"

    return {
        "topic_title": title,
        "topic_summary": summary,
        "source_type": source_type,
        "estimated_virality": virality,
    }


def _parse_topics_from_response(content: str, source_type: str) -> list[dict]:
    """Extract topic objects from Perplexity response text."""
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

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cleaned = re.sub(r"^[\d\.\-\*]+\s*", "", line)
        if len(cleaned) < 15:
            continue
        if ":" in cleaned:
            title, summary = cleaned.split(":", 1)
            topics.append(
                {
                    "topic_title": title.strip(),
                    "topic_summary": summary.strip(),
                    "source_type": source_type,
                    "estimated_virality": "medium",
                }
            )
        else:
            topics.append(
                {
                    "topic_title": cleaned[:120],
                    "topic_summary": f"Trending topic: {cleaned}",
                    "source_type": source_type,
                    "estimated_virality": "medium",
                }
            )

    return topics[:20]


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

    topics.sort(key=lambda t: VIRALITY_ORDER.get(t["estimated_virality"], 2))
    return topics[:30]


def _log_perplexity_cost(data: dict) -> None:
    usage = data.get("usage", {})
    cost = usage.get("cost", {})
    total = cost.get("total_cost")
    if total is not None:
        print(f"   Perplexity cost: ${total:.4f} (search_context: {usage.get('search_context_size', 'unknown')})")


async def _query_perplexity_batch(client: httpx.AsyncClient, api_key: str) -> list[dict]:
    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [{"role": "user", "content": BATCHED_RESEARCH_PROMPT}],
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
    return _parse_topics_from_response(content, "trend")


async def fetch_topics() -> list[dict]:
    """Fetch trending topics from Perplexity and merge manual overrides."""
    manual_topics = _load_manual_topics()
    api_key = os.getenv("PERPLEXITY_API_KEY")

    if not api_key:
        print("⚠️ PERPLEXITY_API_KEY not set — using fallback topics only")
        combined = manual_topics + FALLBACK_TOPICS
        return _ensure_topic_count(combined)

    skip_perplexity = os.getenv("PERPLEXITY_SKIP", "").lower() in ("1", "true", "yes")
    if skip_perplexity:
        print("   PERPLEXITY_SKIP enabled — using fallbacks + manual topics only")
        combined = manual_topics + FALLBACK_TOPICS[:5]
        return _ensure_topic_count(combined)

    researched_topics: list[dict] = []

    try:
        async with httpx.AsyncClient() as client:
            researched_topics = await _query_perplexity_batch(client, api_key)

        if not researched_topics:
            raise RuntimeError("Perplexity returned no topics")

    except Exception as exc:
        print(f"⚠️ Perplexity API failed: {exc}")
        print("   Falling back to evergreen topics + manual overrides")
        researched_topics = list(FALLBACK_TOPICS[:5])

    combined = manual_topics + researched_topics
    final = _ensure_topic_count(combined)
    print(f"   Research complete: {len(final)} topics (min 15, max 30)")
    return final

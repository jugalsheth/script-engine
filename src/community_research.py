"""Community signal research — HN Algolia + Reddit public JSON + mashup + TLDR seeds.

No Reddit OAuth required. Perplexity is used only as optional enrichment elsewhere.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import httpx

from src.series_calendar import get_active_series, mashup_watchlist
from src.tldr_feed import (
    TLDR_AI_RSS_FALLBACK,
    TLDR_AI_RSS_PRIMARY,
    USER_AGENT as TLDR_UA,
    is_sponsor_title,
    matches_builder_lens,
    parse_rss_items,
)

USER_AGENT = (
    "CreatorAuto/1.0 (educational research bot; +https://github.com/local/creatorauto)"
)
HN_SEARCH = "https://hn.algolia.com/api/v1/search"
REDDIT_HOT = "https://www.reddit.com/r/{sub}/hot.json?limit=25"
REDDIT_HOT_OLD = "https://old.reddit.com/r/{sub}/hot.json?limit=25"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed(
    *,
    title: str,
    summary: str,
    source_type: str,
    virality: str,
    url: str = "",
    platform: str = "",
    engagement: float = 0.0,
    format_hint: str = "hack",
    story_hook: str = "",
) -> dict[str, Any]:
    return {
        "topic_title": title[:160],
        "topic_summary": summary[:500],
        "source_type": source_type,
        "estimated_virality": virality,
        "story_hook": story_hook or title[:120],
        "protagonist": "a builder",
        "tension": "",
        "payoff": "one concrete tip the viewer can try today",
        "source_url": url,
        "source_platform": platform,
        "engagement_score": engagement,
        "format_hint": format_hint,
        "researched_at": _now_iso(),
    }


def _virality_from_score(score: float) -> str:
    if score >= 200:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


async def fetch_hn_topics(
    client: httpx.AsyncClient,
    queries: list[str] | None = None,
) -> list[dict]:
    series = get_active_series()
    queries = queries or (series.get("hn_queries") if series else None) or [
        "Cursor",
        "Claude Code",
        "MCP",
        "vibe coding",
    ]
    topics: list[dict] = []
    for q in queries[:4]:
        url = f"{HN_SEARCH}?query={quote_plus(q)}&tags=story&hitsPerPage=8"
        try:
            resp = await client.get(url, timeout=20.0)
            resp.raise_for_status()
            hits = resp.json().get("hits") or []
        except Exception as exc:
            print(f"   ⚠️ HN search failed for {q!r}: {exc}")
            continue

        for hit in hits:
            title = (hit.get("title") or "").strip()
            if not title:
                continue
            points = float(hit.get("points") or 0)
            comments = float(hit.get("num_comments") or 0)
            engagement = points + comments * 0.5
            object_id = hit.get("objectID")
            hn_url = f"https://news.ycombinator.com/item?id={object_id}" if object_id else (
                hit.get("url") or ""
            )
            topics.append(
                _seed(
                    title=title,
                    summary=f"HN discussion ({int(points)} pts): {title}. Query lens: {q}.",
                    source_type="social",
                    virality=_virality_from_score(engagement),
                    url=hn_url,
                    platform="hackernews",
                    engagement=engagement,
                    format_hint="news" if "show hn" in title.lower() else "hack",
                )
            )
    return topics


async def fetch_reddit_topics(
    client: httpx.AsyncClient,
    subreddits: list[str] | None = None,
) -> list[dict]:
    series = get_active_series()
    subs = subreddits or (series.get("subreddits") if series else None) or [
        "CursorAI",
        "ClaudeAI",
        "ChatGPTCoding",
    ]
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    topics: list[dict] = []

    for sub in subs:
        fetched = False
        for url in (REDDIT_HOT.format(sub=sub), REDDIT_HOT_OLD.format(sub=sub)):
            try:
                resp = await client.get(url, headers=headers, timeout=20.0)
                if resp.status_code in (403, 429):
                    continue
                resp.raise_for_status()
                children = (resp.json().get("data") or {}).get("children") or []
                fetched = True
            except Exception as exc:
                print(f"   ⚠️ Reddit r/{sub} failed ({url.split('/')[2]}): {exc}")
                continue

            for child in children:
                data = child.get("data") or {}
                if data.get("stickied"):
                    continue
                title = (data.get("title") or "").strip()
                if not title:
                    continue
                score = float(data.get("score") or 0)
                comments = float(data.get("num_comments") or 0)
                engagement = score + comments
                permalink = data.get("permalink") or ""
                post_url = f"https://www.reddit.com{permalink}" if permalink else ""
                selftext = (data.get("selftext") or "")[:280]
                summary = selftext or f"Hot on r/{sub}: {title}"
                hint = "tip"
                lower = title.lower()
                if any(w in lower for w in ("hack", "mcp", "built", "shipped", "workflow")):
                    hint = "hack"
                elif any(w in lower for w in ("cost", "price", "token", "overspend", "bill")):
                    hint = "confession"
                elif any(w in lower for w in ("update", "release", "changelog", "new")):
                    hint = "news"

                topics.append(
                    _seed(
                        title=title,
                        summary=summary,
                        source_type="social",
                        virality=_virality_from_score(engagement),
                        url=post_url,
                        platform=f"reddit/{sub}",
                        engagement=engagement,
                        format_hint=hint,
                        story_hook=title[:120],
                    )
                )
            break
        if not fetched:
            print(f"   ⚠️ Reddit blocked r/{sub} — using HN/mashups only for that sub")
    return topics


def mashup_seed_topics() -> list[dict]:
    """Synthetic high-intent mashup seeds from the watchlist (always on-niche)."""
    topics: list[dict] = []
    for mashup in mashup_watchlist():
        topics.append(
            _seed(
                title=f"Hack: {mashup}",
                summary=(
                    f"Show builders how to wire {mashup} end-to-end — "
                    "one concrete setup, one visible outcome, try it today."
                ),
                source_type="hack",
                virality="high",
                platform="watchlist",
                engagement=100.0,
                format_hint="hack",
                story_hook=f"You can use {mashup} to ship something visible this week.",
            )
        )
    return topics


def _tldr_feed_urls(series: dict | None) -> list[str]:
    configured = (series or {}).get("tldr_feeds") if series else None
    if isinstance(configured, list) and configured:
        return [str(u) for u in configured if u]
    return [TLDR_AI_RSS_PRIMARY, TLDR_AI_RSS_FALLBACK]


async def fetch_tldr_topics(
    client: httpx.AsyncClient,
    *,
    max_items: int = 12,
) -> list[dict]:
    """TLDR AI newsletter → ACTIONABLE_NEWS seeds (RSS; no Gmail)."""
    series = get_active_series()
    keywords = list((series or {}).get("theme_keywords") or [])
    topics: list[dict] = []
    headers = {"User-Agent": TLDR_UA or USER_AGENT}

    for feed_url in _tldr_feed_urls(series):
        try:
            resp = await client.get(feed_url, headers=headers, timeout=25.0)
            if resp.status_code != 200 or not resp.content:
                print(f"   ⚠️ TLDR feed HTTP {resp.status_code}: {feed_url}")
                continue
            items = parse_rss_items(resp.content)
        except Exception as exc:
            print(f"   ⚠️ TLDR feed failed ({feed_url}): {exc}")
            continue

        for item in items:
            title = item.get("title") or ""
            if not title or is_sponsor_title(title):
                continue
            summary = item.get("summary") or f"From TLDR AI: {title}"
            if not matches_builder_lens(title, summary, keywords):
                continue
            url = (item.get("link") or item.get("archive_url") or "").strip()
            age = item.get("age_days")
            # Prefer fresher issues; still allow undated
            engagement = 90.0 if age is not None and age <= 3 else 55.0
            seed = _seed(
                title=title,
                summary=summary,
                source_type="news",
                virality="high" if engagement >= 80 else "medium",
                url=url,
                platform="tldr",
                engagement=engagement,
                format_hint="news",
                story_hook=f"TLDR flagged: {title[:100]}",
            )
            seed["seed_origin"] = "fresh"
            topics.append(seed)
            if len(topics) >= max_items:
                break
        if topics:
            print(f"   TLDR: {len(topics)} builder-lens stories from {feed_url}")
            break

    if not topics:
        print("   ⚠️ TLDR: no builder-lens stories (feeds down or filtered empty)")
    return topics


async def fetch_community_topics() -> list[dict]:
    """Fetch and merge community topics, ranked by engagement."""
    async with httpx.AsyncClient() as client:
        hn, reddit, tldr = await asyncio.gather(
            fetch_hn_topics(client),
            fetch_reddit_topics(client),
            fetch_tldr_topics(client),
        )

    # Stamp seed_origin for weekly split metadata
    for t in hn + reddit + tldr:
        t.setdefault("seed_origin", "fresh")
    mashups = mashup_seed_topics()
    for t in mashups:
        t.setdefault("seed_origin", "fresh")

    # Prefer TLDR near the top of the fresh pool (after mashups)
    combined = mashups + tldr + hn + reddit
    # Dedupe by title
    seen: set[str] = set()
    unique: list[dict] = []
    for t in combined:
        key = t["topic_title"].lower().strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(t)

    unique.sort(key=lambda t: float(t.get("engagement_score") or 0), reverse=True)
    print(
        f"   Community research: {len(tldr)} TLDR + {len(hn)} HN + {len(reddit)} Reddit + "
        f"{len(mashups)} mashups → {len(unique)} unique"
    )
    return unique[:40]

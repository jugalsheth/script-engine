"""TLDR AI newsletter feed helpers — RSS parse + accessibility probe."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree.ElementTree import Element

import httpx

USER_AGENT = (
    "CreatorAuto/1.0 (educational research bot; +https://github.com/local/creatorauto)"
)

# Primary: per-story items, usually fresh (may lack per-item links)
TLDR_AI_RSS_PRIMARY = "https://bullrich.dev/tldr-rss/ai.rss"
# Fallback: dated issue digests with archive links (mirror can lag)
TLDR_AI_RSS_FALLBACK = (
    "https://raw.githubusercontent.com/alan-turing-institute/ai-rss-feeds/"
    "refs/heads/main/feeds/tldr-ai.xml"
)
TLDR_AI_ARCHIVE = "https://tldr.tech/ai/archives"

SPONSOR_RE = re.compile(r"\bsponsor\b", re.I)
BUILDER_KEYWORDS = (
    "cursor",
    "claude",
    "anthropic",
    "openai",
    "agent",
    "mcp",
    "token",
    "coding",
    "code",
    "devin",
    "swe",
    "github",
    "copilot",
    "composer",
    "llm",
    "model",
    "api",
    "prompt",
    "vibe",
)


def is_sponsor_title(title: str) -> bool:
    return bool(SPONSOR_RE.search(title or ""))


def _text(el: Element | None) -> str:
    if el is None:
        return ""
    return (el.text or "").strip()


def _child_text(item: Element, *names: str) -> str:
    for name in names:
        for child in item:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == name:
                return _text(child)
    return ""


def _archive_url_from_pub(pub: str) -> str:
    if not pub:
        return ""
    try:
        dt = parsedate_to_datetime(pub)
        return f"https://tldr.tech/ai/{dt.date().isoformat()}"
    except (TypeError, ValueError, IndexError):
        return ""


def _age_days(pub: str) -> int | None:
    if not pub:
        return None
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).days)
    except (TypeError, ValueError, IndexError):
        return None


def parse_rss_items(body: bytes | str) -> list[dict[str, Any]]:
    """Normalize RSS <item> rows into title/link/summary/pub/archive_url."""
    if isinstance(body, str):
        body = body.encode("utf-8", errors="replace")
    root = ET.fromstring(body)
    items: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = _child_text(item, "title")
        if not title:
            continue
        link = _child_text(item, "link")
        summary = _child_text(item, "description", "summary")
        # Strip crude HTML
        summary = re.sub(r"<[^>]+>", " ", summary)
        summary = re.sub(r"\s+", " ", summary).strip()
        pub = _child_text(item, "pubDate", "published", "date")
        archive = ""
        if "tldr.tech/ai/" in link:
            archive = link
        else:
            archive = _archive_url_from_pub(pub)
        items.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
                "pub": pub,
                "archive_url": archive,
                "age_days": _age_days(pub),
            }
        )
    return items


def probe_feed(url: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """Live HTTP + parse probe used by the accessibility gate."""
    result: dict[str, Any] = {
        "url": url,
        "ok": False,
        "status": None,
        "item_count": 0,
        "story_count": 0,
        "age_days": None,
        "error": None,
    }
    try:
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            resp = client.get(url)
        result["status"] = resp.status_code
        if resp.status_code != 200 or not resp.content:
            result["error"] = f"HTTP {resp.status_code} or empty body"
            return result
        items = parse_rss_items(resp.content)
        result["item_count"] = len(items)
        stories = [i for i in items if not is_sponsor_title(i["title"])]
        result["story_count"] = len(stories)
        if stories:
            ages = [i["age_days"] for i in stories if i.get("age_days") is not None]
            result["age_days"] = min(ages) if ages else None
        result["ok"] = result["story_count"] >= 1
    except Exception as exc:  # noqa: BLE001 — probe must never raise for callers
        result["error"] = str(exc)
    return result


def matches_builder_lens(title: str, summary: str, keywords: list[str] | None = None) -> bool:
    blob = f"{title} {summary}".lower()
    keys = [k.lower() for k in (keywords or []) if k] or list(BUILDER_KEYWORDS)
    return any(k in blob for k in keys)

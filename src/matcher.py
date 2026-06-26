from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JOURNAL_CONFIG_PATH = CONFIG_DIR / "journal_config.json"
QUEUE_PATH = DATA_DIR / "personal_topics_queue.json"
JOURNAL_DIR = DATA_DIR / "journal"

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "shall", "can",
    "it", "its", "this", "that", "these", "those", "i", "me", "my", "we",
    "our", "you", "your", "he", "she", "they", "them", "their", "what",
    "which", "who", "when", "where", "why", "how", "all", "each", "every",
    "both", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "about", "into", "through", "during", "before", "after", "above",
    "below", "up", "down", "out", "off", "over", "under", "again", "then",
    "once", "here", "there", "also", "back", "even", "still", "well",
    "like", "really", "think", "know", "want", "need", "going", "got",
    "get", "make", "made", "say", "said", "tell", "told", "thing", "things",
}

KNOWLEDGE_DOMAINS = {
    "data_engineering": [
        "pipeline", "ETL", "data", "Snowflake", "warehouse",
        "CDC", "stream", "batch", "query", "SQL", "database",
    ],
    "cloud_aws": [
        "AWS", "Lambda", "serverless", "cloud", "infrastructure",
        "SQS", "API", "deployment", "architecture",
    ],
    "full_stack": [
        "full-stack", "app", "frontend", "backend", "Next.js",
        "React", "TypeScript", "API endpoint", "application",
    ],
    "career_growth": [
        "career", "salary", "job", "hiring", "recruiter",
        "LinkedIn", "resume", "interview", "skill", "engineer",
    ],
    "ai_ml": [
        "AI", "LLM", "machine learning", "Claude", "OpenAI", "agent",
        "automation", "prompt", "model", "artificial intelligence",
    ],
    "productivity": [
        "productivity", "workflow", "automation", "system",
        "process", "efficiency", "tool", "framework",
    ],
    "money_finance": [
        "salary", "money", "income", "wealth", "invest",
        "finance", "budget", "compensation", "pay",
    ],
}

DOMAIN_TO_TERRITORY = {
    "data_engineering": "Tech Made Simple",
    "cloud_aws": "Tech Made Simple",
    "full_stack": "Tech Made Simple",
    "career_growth": "Career + Money",
    "ai_ml": "AI Demystified",
    "productivity": "Build Mindset",
    "money_finance": "Career + Money",
}

TERRITORY_KEYWORDS = {
    "Tech Made Simple": ["technical", "explain", "simple", "sql", "code", "data", "api"],
    "Career + Money": ["career", "salary", "job", "money", "compensation", "negotiate"],
    "AI Demystified": ["ai", "llm", "machine learning", "model", "claude", "openai"],
    "Build Mindset": ["mindset", "decision", "engineer", "think", "problem"],
    "Learning Fast": ["learn", "skill", "study", "bootcamp", "course"],
    "NYC + Ambition": ["nyc", "new york", "ambition", "competitive"],
    "Practitioner Insider": ["team", "production", "insider", "workplace", "manager"],
    "Future of Work": ["future", "jobs", "work", "automation", "disappear"],
    "Systems Thinking": ["system", "framework", "process", "workflow"],
}


def _load_territories() -> list[str]:
    territories_path = CONFIG_DIR / "territories.txt"
    try:
        lines = territories_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return list(TERRITORY_KEYWORDS.keys())
    return [line.split("—")[0].strip() for line in lines if line.strip()]


def _count_keyword_matches(text: str) -> tuple[int, str | None]:
    """Return total match count and best-matching domain name."""
    text_lower = text.lower()
    best_domain = None
    best_count = 0
    total = 0

    for domain, keywords in KNOWLEDGE_DOMAINS.items():
        domain_count = sum(1 for kw in keywords if kw.lower() in text_lower)
        total += domain_count
        if domain_count > best_count:
            best_count = domain_count
            best_domain = domain

    return total, best_domain


def _match_territory(text: str, best_domain: str | None) -> str:
    if best_domain and best_domain in DOMAIN_TO_TERRITORY:
        return DOMAIN_TO_TERRITORY[best_domain]

    text_lower = text.lower()
    best_territory = "General"
    best_score = 0

    for territory, keywords in TERRITORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            best_territory = territory

    return best_territory


def score_topics(topics: list[dict]) -> list[dict]:
    """Score topics against knowledge domains and sort by relevance."""
    _load_territories()
    scored: list[dict] = []

    for topic in topics:
        text = f"{topic.get('topic_title', '')} {topic.get('topic_summary', '')}"
        score, best_domain = _count_keyword_matches(text)
        territory = _match_territory(text, best_domain) if score >= 1 else "General"

        enriched = dict(topic)
        enriched["match_score"] = score
        enriched["territory"] = territory
        scored.append(enriched)

    scored.sort(key=lambda t: t["match_score"], reverse=True)
    return scored


def _load_journal_config() -> dict:
    try:
        return json.loads(JOURNAL_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "dedup_lookback_days": 14,
            "keyword_overlap_threshold": 0.6,
            "reserved_slots": {"intro": 1, "growth": 3},
        }


def domain_tags_for_text(text: str) -> list[str]:
    """Return domains with keyword hits, sorted by hit count descending."""
    text_lower = text.lower()
    hits: list[tuple[str, int]] = []
    for domain, keywords in KNOWLEDGE_DOMAINS.items():
        count = sum(1 for kw in keywords if kw.lower() in text_lower)
        if count > 0:
            hits.append((domain, count))
    hits.sort(key=lambda x: x[1], reverse=True)
    return [d for d, _ in hits]


def dominant_domain_tag(text: str) -> str | None:
    tags = domain_tags_for_text(text)
    return tags[0] if tags else None


def _distinctive_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 2 and t not in STOPWORDS}


def keyword_overlap_ratio(text_a: str, text_b: str) -> float:
    """Jaccard overlap on distinctive tokens."""
    a = _distinctive_tokens(text_a)
    b = _distinctive_tokens(text_b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _load_queue() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not QUEUE_PATH.exists():
        QUEUE_PATH.write_text("[]\n", encoding="utf-8")
        return []
    try:
        data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_queue(queue: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")


def load_recent_journal_entries(lookback_days: int | None = None) -> list[dict]:
    """Load journal lines from the last N days across monthly files."""
    config = _load_journal_config()
    days = lookback_days if lookback_days is not None else config.get("dedup_lookback_days", 14)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entries: list[dict] = []
    if not JOURNAL_DIR.exists():
        return entries
    for path in sorted(JOURNAL_DIR.glob("*.jsonl")):
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                ts = entry.get("timestamp", "")
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if dt >= cutoff:
                    entries.append(entry)
        except (OSError, json.JSONDecodeError):
            continue
    return entries


def find_duplicate_queue_entry(
    text: str,
    queue: list[dict] | None = None,
    journal_recent: list[dict] | None = None,
) -> dict | None:
    """Find queue entry with same dominant domain and high keyword overlap."""
    config = _load_journal_config()
    threshold = config.get("keyword_overlap_threshold", 0.6)
    if queue is None:
        queue = _load_queue()
    if journal_recent is None:
        journal_recent = load_recent_journal_entries()

    dominant = dominant_domain_tag(text)
    if not dominant:
        return None

    candidates: list[dict] = [
        e for e in queue if not e.get("processed", False)
    ]
    for entry in journal_recent:
        qid = entry.get("queue_id")
        if qid:
            match = next((q for q in queue if q.get("id") == qid and not q.get("processed")), None)
            if match and match not in candidates:
                candidates.append(match)

    for candidate in candidates:
        cand_tags = candidate.get("domain_tags") or domain_tags_for_text(candidate.get("raw_text", ""))
        if dominant not in cand_tags:
            continue
        if keyword_overlap_ratio(text, candidate.get("raw_text", "")) >= threshold:
            return candidate
    return None


def queue_entry_from_transcript(
    raw_text: str,
    timestamp: str | None = None,
) -> dict:
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": str(uuid.uuid4()),
        "first_captured": ts,
        "raw_text": raw_text,
        "related_mentions": [],
        "domain_tags": domain_tags_for_text(raw_text),
        "custom_visual_requests": [],
        "processed": False,
        "used_in_script": None,
    }


def journal_topic_from_queue(entry: dict) -> dict:
    """Convert queue entry to topic dict for generator."""
    raw = entry.get("raw_text", "")
    tags = entry.get("domain_tags") or domain_tags_for_text(raw)
    dominant = tags[0] if tags else None
    territory = DOMAIN_TO_TERRITORY.get(dominant, "General") if dominant else "General"
    title_preview = raw[:60].strip()
    if len(raw) > 60:
        title_preview += "..."
    return {
        "topic_title": f"Journal: {title_preview}",
        "topic_summary": raw[:500],
        "source_type": "journal",
        "territory": territory,
        "raw_transcript": raw,
        "queue_id": entry.get("id"),
        "domain_tags": tags,
        "match_score": len(tags) * 2,
    }


def count_pending_queue() -> int:
    """Count unprocessed personal topic queue entries."""
    return sum(1 for e in _load_queue() if not e.get("processed", False))


def pull_queue_entries(n: int) -> list[dict]:
    """Oldest unprocessed queue entries first."""
    queue = _load_queue()
    pending = [e for e in queue if not e.get("processed", False)]
    pending.sort(key=lambda e: e.get("first_captured", ""))
    return [journal_topic_from_queue(e) for e in pending[:n]]


def mark_queue_consumed(journal_topics: list[dict], scripts: list[dict]) -> None:
    """Mark queue entries processed after successful script generation."""
    queue = _load_queue()
    queue_by_id = {e["id"]: e for e in queue if "id" in e}
    changed = False

    for topic in journal_topics:
        qid = topic.get("queue_id")
        if not qid or qid not in queue_by_id:
            continue
        script = next((s for s in scripts if s.get("queue_id") == qid), None)
        if script:
            entry = queue_by_id[qid]
            entry["processed"] = True
            entry["used_in_script"] = script.get("filename_hint")
            changed = True

    if changed:
        save_queue(queue)


def update_queue_visual_requests(queue_id: str, visual_requests: list[dict]) -> None:
    """Store extracted visual requests on the queue entry for audit trail."""
    if not queue_id or not visual_requests:
        return
    queue = _load_queue()
    for entry in queue:
        if entry.get("id") == queue_id:
            entry["custom_visual_requests"] = visual_requests
            save_queue(queue)
            return

from __future__ import annotations

from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

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

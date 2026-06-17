"""Batched Perplexity enrichment for journal-sourced topics (one API call per run)."""

from __future__ import annotations

import json
import os
import re

import httpx

from src.matcher import _load_journal_config
from src.research import PERPLEXITY_API_URL, PERPLEXITY_MODEL, _log_perplexity_cost

ENRICH_PROMPT = """You enrich creator journal rambles with timely news context for 60-second tech reels.

For EACH ramble below, find what is relevant THIS WEEK (news, deals, discourse, hiring data).
Return a JSON array with one object per ramble IN THE SAME ORDER. Each object must have:
- queue_id (string — copy exactly from input)
- timely_context (2-3 sentences: recent news tied to the ramble; name sources briefly)
- hook_angles (array of 2 short hook lines blending ramble + timeliness; creator's POV stays primary)
- stats_to_weave (array of 0-2 verifiable stats with source names; empty array if none found)

Rules:
- Do NOT replace or genericize the creator's story
- Do NOT invent statistics
- hook_angles are optional spice — the ramble remains the core story

Rambles:
{rambles_json}

Return ONLY valid JSON array, no markdown."""


def _enrichment_enabled() -> bool:
    if os.getenv("JOURNAL_ENRICH_SKIP", "").lower() in ("1", "true", "yes"):
        return False
    config = _load_journal_config()
    return bool(config.get("enrich_journal", True))


def _build_ramble_payload(topics: list[dict]) -> list[dict]:
    payload = []
    for topic in topics:
        if topic.get("source_type") != "journal":
            continue
        qid = topic.get("queue_id")
        raw = topic.get("raw_transcript", topic.get("topic_summary", ""))
        if not qid or not raw:
            continue
        payload.append({
            "queue_id": qid,
            "preview": raw[:800],
            "domain_tags": topic.get("domain_tags", []),
        })
    return payload


def _parse_enrichment_response(content: str) -> list[dict]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", cleaned)
        if not match:
            return []
        try:
            parsed = json.loads(match.group())
        except json.JSONDecodeError:
            return []

    if not isinstance(parsed, list):
        return []

    results: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict) or not item.get("queue_id"):
            continue
        stats = item.get("stats_to_weave") or []
        hooks = item.get("hook_angles") or []
        results.append({
            "queue_id": str(item["queue_id"]),
            "timely_context": str(item.get("timely_context", "")).strip(),
            "hook_angles": [str(h).strip() for h in hooks if str(h).strip()][:2],
            "stats_to_weave": [str(s).strip() for s in stats if str(s).strip()][:2],
        })
    return results


def _merge_enrichment(topics: list[dict], enrichments: list[dict]) -> list[dict]:
    by_id = {e["queue_id"]: e for e in enrichments}
    merged: list[dict] = []
    for topic in topics:
        updated = dict(topic)
        entry = by_id.get(topic.get("queue_id", ""))
        if entry and entry.get("timely_context"):
            updated["journal_enrichment"] = entry
        merged.append(updated)
    return merged


async def enrich_journal_topics(topics: list[dict]) -> list[dict]:
    """Add timely news context to journal topics via one batched Perplexity call."""
    journal_only = [t for t in topics if t.get("source_type") == "journal"]
    if not journal_only or not _enrichment_enabled():
        if journal_only and not _enrichment_enabled():
            print("   Journal enrich: skipped (disabled)")
        return topics

    api_key = os.getenv("PERPLEXITY_API_KEY", "").strip()
    if not api_key:
        print("   Journal enrich: skipped (PERPLEXITY_API_KEY not set)")
        return topics

    payload = _build_ramble_payload(journal_only)
    if not payload:
        return topics

    print(f"   Journal enrich: researching {len(payload)} ramble(s) (batched)...")
    prompt = ENRICH_PROMPT.format(rambles_json=json.dumps(payload, indent=2))

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                PERPLEXITY_API_URL,
                json={
                    "model": PERPLEXITY_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 1200,
                    "web_search_options": {"search_context_size": "low"},
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=90.0,
            )
            response.raise_for_status()
            data = response.json()
            _log_perplexity_cost(data)
            content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"   Journal enrich: failed ({exc}) — continuing without enrichment")
        return topics

    enrichments = _parse_enrichment_response(content)
    enriched_count = sum(1 for e in enrichments if e.get("timely_context"))
    print(f"   Journal enrich: {enriched_count}/{len(payload)} ramble(s) enriched")
    return _merge_enrichment(topics, enrichments)

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import anthropic

from src import hook_bank
from src.content_phase import get_phase, get_videos_published

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
SONNET_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 2000

JSON_FIELDS = """
  "title_overlay": "THE BOLD TITLE IN CAPS",
  "subtitle_overlay": "short descriptive subtitle",
  "spoken_script": "The complete word-for-word script the creator reads...",
  "caption_hook": "One compelling sentence for Instagram/LinkedIn caption",
  "hashtags": ["#Tag1", "#Tag2", "#Tag3", "#Tag4", "#Tag5"],
  "series_note": "Episode X of 4: Building the Brand — or null if standalone",
  "recording_tip": "One sentence tip for delivery",
  "hook_type": "which of the 4 patterns used",
  "opening_line": "the exact first sentence spoken",
  "open_loop_plant": "the teaser line planted early in the script",
  "open_loop_payoff": "how and where the loop resolves",
  "loopback_closer": "final line that connects back to the hook",
  "visual_cues": "3-4 specific on-screen graphic moments tied to exact moments in the script",
  "delivery_notes": "pace, pause, and emphasis cues for recording",
  "retention_notes": "where the loop plants and pays off, rhythm break, mid-video re-hook moment"
"""


def _load_config_file(filename: str) -> str:
    path = CONFIG_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"⚠️ Could not read {filename}: {exc}")
        return ""


def _parse_script_json(content: str) -> dict | None:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        json_match = re.search(r"\{[\s\S]*\}", cleaned)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
    return None


def _intro_requirements(brand_episode: int) -> str:
    return (
        f"CONTENT PHASE: INTRO (Brand episode {brand_episode} of 4)\n"
        "This is a brand-building video for a creator just starting out.\n"
        "Goal: build trust and relatability — NOT hot takes or contrarian punches yet.\n\n"
        "SPOKEN SCRIPT REQUIREMENTS — INTRO MODE:\n"
        "Follow Hook → Problem → Solution → CTA. Include ALL:\n\n"
        "1. HOOK — use ONLY one of these patterns:\n"
        "   - IDENTITY CALL: name exactly who this is for\n"
        "   - CONFESSION: admit something real and specific\n"
        "   - OPEN LOOP: pose a question, answer it later (use sparingly)\n"
        "   Do NOT use CONTRARIAN STRIKE in intro phase.\n"
        '   NEVER open with "Hey guys", "In this video", or any warmup.\n'
        "   NEVER reuse any opening line from recent_hooks list provided.\n\n"
        "2. OPEN LOOP — plant a soft question in the first 10 seconds.\n"
        "   Resolve it near the end. Keep it personal, not aggressive.\n\n"
        "3. THREE ACTION STEPS — simple and doable. At least one doable TODAY.\n"
        "   Stats optional in intro — personal experience beats data here.\n\n"
        "4. TONE — warm, honest, peer-to-peer. 'I'm sharing what I've learned'\n"
        "   not 'I'm the expert broadcasting wisdom'.\n\n"
        "5. LOOP-BACK CLOSER — final line connects back to the opening hook.\n\n"
        "6. LENGTH — 120-140 words (~45-55 seconds). Shorter is fine for intro.\n\n"
        "7. VISUAL CUES — keep simple: talking head + bold text overlays only.\n"
        "   No b-roll, no screen recordings, no complex animations.\n"
        "   Suggest: title card at 0:00, subtitle at 0:05, step cards at steps.\n\n"
        f'- series_note must be: "Brand intro {brand_episode} of 4"\n'
        "- Written in first person, casual, direct\n"
        "- No bullet points in spoken_script — continuous speech\n"
        "- opening_line must match the first sentence of spoken_script exactly\n"
        "- loopback_closer must match the final sentence of spoken_script exactly"
    )


def _growth_requirements() -> str:
    return (
        "CONTENT PHASE: GROWTH (Video 5+)\n"
        "Full retention framework — this is where you go hard.\n\n"
        "SPOKEN SCRIPT REQUIREMENTS — GROWTH MODE:\n"
        "Every script must follow Hook → Problem → Solution → CTA. Include ALL:\n\n"
        "1. HOOK (first 3 seconds) — use exactly ONE of these 4 proven patterns:\n"
        "   - IDENTITY CALL: name exactly who this is for\n"
        "   - CONTRARIAN STRIKE: state something against consensus\n"
        "   - OPEN LOOP: pose a question, answer it later\n"
        "   - CONFESSION: admit something real and specific\n"
        '   NEVER open with "Hey guys", "In this video", or any warmup.\n'
        "   NEVER reuse any opening line from recent_hooks list provided.\n\n"
        "2. OPEN LOOP (Zeigarnik Effect) — plant an unresolved question in\n"
        "   the first 10 seconds. Resolve it near the end. Mandatory.\n\n"
        "3. THREE ACTION STEPS — specific, doable THIS WEEK. At least one real\n"
        "   statistic with source named out loud. Not awareness — ACTION.\n\n"
        '4. CASCADING PAYOFFS — each step resolves AND tees up the next\n'
        '   ("that fixes X, but now you have Y — which is step two").\n\n'
        "5. RHYTHM VARIATION — alternate sentence length. Short. Longer. Short.\n\n"
        "6. LOOP-BACK CLOSER — final line connects back to the opening hook.\n\n"
        "7. LENGTH — 150-160 words (~60 seconds). Conversational, never a lecture.\n\n"
        "8. VISUAL CUES — include stat pop, step cards, and optional b-roll moments\n"
        "   (blurred LinkedIn screenshot, terminal, etc.) tied to exact timestamps.\n\n"
        "- Written in first person, casual, direct\n"
        "- No bullet points in spoken_script — continuous speech\n"
        "- opening_line must match the first sentence of spoken_script exactly\n"
        "- loopback_closer must match the final sentence of spoken_script exactly"
    )


def _build_user_prompt(
    topic: dict,
    script_number: int,
    recent_hooks: list[str],
    phase: str,
    brand_episode: int,
) -> str:
    territory = topic.get("territory", "General")
    hooks_block = (
        json.dumps(recent_hooks, indent=2)
        if recent_hooks
        else "[] (none yet — you have full creative freedom)"
    )
    requirements = (
        _intro_requirements(brand_episode)
        if phase == "intro"
        else _growth_requirements()
    )

    return (
        f"Generate a complete video script for the following topic:\n"
        f"TOPIC: {topic['topic_title']}\n"
        f"CONTEXT: {topic.get('topic_summary', '')}\n"
        f"TERRITORY: {territory}\n\n"
        f"Avoid reusing any of these recent opening lines: {hooks_block}\n\n"
        f"Return a JSON object with exactly these fields:\n"
        "{\n"
        f'"script_number": {script_number},\n'
        f'"territory": "{territory}",\n'
        f"{JSON_FIELDS.strip()}\n"
        "}\n\n"
        f"{requirements}\n\n"
        "Return ONLY the JSON object. No markdown, no explanation, no backticks."
    )


async def generate_scripts(topics: list[dict], phase: str | None = None) -> list[dict]:
    """Generate video scripts for approved topics using Claude Sonnet."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not set — cannot generate scripts")
        return []

    voice_profile = _load_config_file("voice_profile.txt")
    if not voice_profile:
        print("❌ voice_profile.txt missing — cannot generate scripts")
        return []

    phase = phase or get_phase()
    videos_published = get_videos_published()
    print(f"   Phase: {phase.upper()} ({videos_published}/4 videos published)")

    recent_hooks = hook_bank.get_recent_hooks(30)
    if recent_hooks:
        print(f"   Avoiding {len(recent_hooks)} recent hook(s) from hook bank")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    scripts: list[dict] = []

    for i, topic in enumerate(topics, start=1):
        brand_episode = videos_published + i if phase == "intro" else i
        print(
            f"   Generating script {i}/{len(topics)} "
            f"[{phase}] {topic['topic_title'][:45]}..."
        )
        try:
            response = await client.messages.create(
                model=SONNET_MODEL,
                max_tokens=MAX_TOKENS,
                system=voice_profile,
                messages=[
                    {
                        "role": "user",
                        "content": _build_user_prompt(
                            topic, i, recent_hooks, phase, brand_episode
                        ),
                    }
                ],
            )
            content = response.content[0].text
            script = _parse_script_json(content)

            if not script:
                print(f"⚠️ Failed to parse JSON for script {i}")
                continue

            script["script_number"] = script.get("script_number", i)
            script["territory"] = script.get("territory", topic.get("territory", "General"))
            script["source_topic"] = topic["topic_title"]
            script["content_phase"] = phase
            if phase == "intro":
                script["brand_episode"] = f"{brand_episode} of 4"
            scripts.append(script)

        except Exception as exc:
            print(f"⚠️ Script generation failed for topic {i}: {exc}")
            continue

    if scripts:
        hook_bank.save_hooks(scripts)
        save_scripts_archive(scripts)

    return scripts


def save_scripts_archive(scripts: list) -> None:
    """
    Saves the generated script batch to data/scripts_archive.json.
    Keeps the last 60 scripts (approx 6 weeks of batches).
    Each script gets a date_generated field added.
    File size will never exceed ~200KB — safe for GitHub storage.
    """
    from pathlib import Path
    from datetime import date
    import json

    archive_path = Path("data/scripts_archive.json")
    archive_path.parent.mkdir(exist_ok=True)

    # Load existing archive
    try:
        existing = json.loads(archive_path.read_text())
    except Exception:
        existing = []

    # Stamp each new script with today's date
    today = date.today().isoformat()
    stamped = [{**s, "date_generated": today} for s in scripts]

    # Prepend new scripts, keep last 60 total
    updated = stamped + existing
    archive_path.write_text(json.dumps(updated[:60], indent=2))

    print(f"   Saved {len(stamped)} scripts to scripts_archive.json "
          f"({len(updated[:60])} total in archive)")

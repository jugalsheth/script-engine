from __future__ import annotations

import json
import os
import re
from pathlib import Path

import anthropic

from src import hook_bank
from src.content_phase import get_phase, get_videos_published
from src.script_validator import ValidationResult, validate_script

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
SONNET_MODEL = "claude-sonnet-4-20250514"
HAIKU_MODEL = "claude-3-5-haiku-20241022"
MAX_TOKENS = 3200
MAX_GENERATION_ATTEMPTS = 3
MAX_WORDS = 145

HOOK_TO_TEMPLATE = {
    "OPEN LOOP": "THREE_STEP_HOT_TAKE",
    "IDENTITY CALL": "THREE_STEP_HOT_TAKE",
    "CONTRARIAN STRIKE": "THREE_STEP_HOT_TAKE",
    "CONFESSION": "CONFESSION_STAT",
}

JSON_FIELDS = """
  "script_type": "NEWS_REACTION | EVERGREEN_VALUE | HOT_TAKE",
  "creator_take_anchor": "one-line POV from creator_takes.txt (opinion angle, not work story)",
  "work_pattern_id": "null or optional id from work_patterns.txt — only if generalized credibility fits",
  "title_overlay": "THE BOLD TITLE IN CAPS",
  "subtitle_overlay": "short descriptive subtitle",
  "spoken_script": "The complete word-for-word script the creator reads...",
  "caption_hook": "One compelling sentence for Instagram/LinkedIn caption",
  "hashtags": ["#Tag1", "#Tag2", "#Tag3", "#Tag4", "#Tag5"],
  "series_note": "Episode X of 4: Building the Brand — or null if standalone",
  "recording_tip": "Pause before numbers. First line with energy, not presentation voice. One more specific tip.",
  "hook_type": "IDENTITY CALL | CONFESSION | OPEN LOOP | CONTRARIAN STRIKE",
  "opening_line": "the exact first sentence spoken",
  "open_loop_plant": "the teaser line planted early in the script",
  "open_loop_payoff": "how and where the loop resolves",
  "loopback_closer": "final line that connects back to the hook",
  "visual_cues": "human-readable summary of graphics (legacy, keep for Telegram)",
  "visual_moments": [
    {"at_phrase": "exact spoken phrase", "graphic": "23", "label": "LABEL CAPS", "type": "stat", "side": "right"}
  ],
  "video_triggers": {
    "stat_phrases": [{"phrase": "twenty three workflows", "display": "23", "label": "AUTOMATED WORKFLOWS"}],
    "fun_phrases": ["that's normal", "pure building"],
    "energy_words": ["right", "truth"],
    "broll_phrases": ["data pipeline", "python script"],
    "beat_phrases": {"crust": "pure building", "payoff": "here's what makes it worth it"}
  },
  "edit_template": "THREE_STEP_HOT_TAKE or CONFESSION_STAT",
  "recording_cues": [
    {"second": 0, "action": "HOOK — lean in, fast, confident. No smile warmup."},
    {"second": 5, "phrase": "here's what's wild", "action": "PAUSE 0.3s then ENERGY UP — crust zoom fires"},
    {"second": 12, "phrase": "seventy four percent", "action": "PAUSE before number, speak clearly"},
    {"second": 22, "action": "STEP 1 — point at camera, punch the word 'first'"},
    {"second": 35, "phrase": "secret", "action": "Hit fun phrase hard"},
    {"second": 48, "action": "CLOSER — slow down, land the loop-back line"}
  ],
  "delivery_notes": "pace, pause, and emphasis cues for recording",
  "retention_notes": "where the loop plants and pays off, rhythm break, mid-video re-hook moment"
"""

FUN_PHRASE_POOL = (
    "that's normal, finally, wrong, secret, truth, pure building, failed, "
    "insane, wild, listen, unless, really"
)


def _load_config_file(filename: str) -> str:
    path = CONFIG_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"⚠️ Could not read {filename}: {exc}")
        return ""


def _build_system_prompt() -> str:
    """Combine voice profile, creator POV bank, and hard content boundaries."""
    parts = [
        _load_config_file("content_philosophy.txt"),
        _load_config_file("voice_profile.txt"),
        _load_config_file("creator_takes.txt"),
        _load_config_file("work_patterns.txt"),
        _load_config_file("content_boundaries.txt"),
    ]
    combined = "\n\n---\n\n".join(p for p in parts if p.strip())
    if not combined.strip():
        print("❌ voice_profile.txt missing — cannot generate scripts")
    return combined


def _script_type_for_topic(topic: dict) -> str:
    if topic.get("source_type") == "news":
        return "NEWS_REACTION"
    title = f"{topic.get('topic_title', '')} {topic.get('topic_summary', '')}".lower()
    hot_keywords = ("wrong", "myth", "overhyped", "hate", "stop", "don't", "shouldn't", "contrarian")
    if any(kw in title for kw in hot_keywords):
        return "HOT_TAKE"
    return "EVERGREEN_VALUE"


def _script_type_requirements(script_type: str, script_number: int, batch_size: int) -> str:
    if script_type == "NEWS_REACTION":
        return (
            "SCRIPT TYPE: NEWS_REACTION\n"
            "- Hook names what happened THIS WEEK in AI/tech (model, layoff trend, hiring shift, tool release)\n"
            "- Explain what it means for engineers, PMs, and builders — broad practitioner value\n"
            "- One actionable step for this week because of the news\n"
            "- Cite source for any fact ('according to...', 'this week's announcement...')\n"
            "- Do NOT imply the creator is job searching\n"
            "- NO niche personal work stories — this is about the NEWS and the VIEWER\n"
            "- work_pattern_id: null\n"
        )
    if script_type == "HOT_TAKE":
        return (
            "SCRIPT TYPE: HOT_TAKE\n"
            "- Open with contrarian claim anchored to a creator_take (DSA, hybrid, builders vs grinders)\n"
            "- Defend with universal logic + optional ONE generalized pattern line from work_patterns.txt\n"
            "- Confident pushback, not biting sarcasm\n"
            "- Never cite fake 'I analyzed N posts' research\n"
        )
    return (
        "SCRIPT TYPE: EVERGREEN_VALUE\n"
        "- Informative first: universal lesson any engineer/PM can use Monday\n"
        "- Hook = pain or insight the VIEWER has — not 'at my company...'\n"
        "- 3 actionable steps — specific tools/skills/habits, not vague awareness\n"
        "- creator_take_anchor = your opinion angle, not a work anecdote\n"
        "- work_pattern_id: null unless script {script_number} is the ONE optional credibility script in batch\n"
        f"- Batch size {batch_size}: at most 1-2 scripts may set work_pattern_id; this is script #{script_number}\n"
        "- If using work_pattern_id: ONE generalized sentence only — see TRANSLATION EXAMPLES in work_patterns.txt\n"
    )


def _slug_words(text: str, max_words: int = 4) -> str:
    words = re.sub(r"[^a-zA-Z0-9 ]", "", text.lower()).split()
    return "_".join(words[:max_words]) or "topic"


def _build_recording_cues(script: dict) -> list[dict]:
    """Fallback teleprompter cues when the model omits recording_cues."""
    triggers = script.get("video_triggers") or {}
    beats = triggers.get("beat_phrases") or {}
    crust = beats.get("crust") or "step one"
    fun_phrases = triggers.get("fun_phrases") or ["wild", "truth"]
    stat_phrases = triggers.get("stat_phrases") or []

    cues: list[dict] = [
        {
            "second": 0,
            "action": "HOOK — lean in, fast, confident. First line with energy, not presentation voice.",
        },
        {
            "second": 5,
            "phrase": crust,
            "action": "PAUSE 0.3s → ENERGY UP. Crust zoom + flash fires here.",
        },
    ]

    sec = 12
    for stat in stat_phrases[:2]:
        phrase = stat.get("phrase", "") if isinstance(stat, dict) else ""
        if phrase:
            cues.append({
                "second": sec,
                "phrase": phrase,
                "action": "PAUSE before number. Speak as words, not digits.",
            })
            sec += 10

    for i, phrase in enumerate(fun_phrases[:2], start=1):
        cues.append({
            "second": sec,
            "phrase": phrase,
            "action": f"FUN FX #{i} — hit this phrase hard.",
        })
        sec += 8

    cues.append({
        "second": max(sec, 42),
        "action": "CLOSER — slow down, land loopback_closer with confidence.",
    })
    return cues


def _normalize_script(script: dict) -> dict:
    """Ensure video-engine contract fields exist with sane defaults."""
    triggers = script.get("video_triggers") or {}
    if not isinstance(triggers, dict):
        triggers = {}
    triggers.setdefault("stat_phrases", [])
    triggers.setdefault("fun_phrases", [])
    triggers.setdefault("energy_words", ["right", "truth"])
    triggers.setdefault("broll_phrases", [])
    triggers.setdefault("logo_phrases", [])
    beats = triggers.get("beat_phrases") or {}
    if not isinstance(beats, dict):
        beats = {}
    if not beats.get("crust"):
        beats["crust"] = "step one"
    triggers["beat_phrases"] = beats
    script["video_triggers"] = triggers

    moments = script.get("visual_moments")
    if not isinstance(moments, list):
        script["visual_moments"] = []

    hook = script.get("hook_type", "OPEN LOOP")
    script.setdefault("edit_template", HOOK_TO_TEMPLATE.get(hook, "THREE_STEP_HOT_TAKE"))

    cues = script.get("recording_cues")
    if not isinstance(cues, list) or len(cues) < 4:
        script["recording_cues"] = _build_recording_cues(script)

    num = script.get("script_number", 1)
    title = script.get("title_overlay", "video")
    script["filename_hint"] = f"script_{int(num):02d}_{_slug_words(title)}.mp4"

    word_count = len(script.get("spoken_script", "").split())
    script["word_count"] = word_count
    script["estimated_seconds"] = round(word_count / 2.6)
    if word_count > MAX_WORDS:
        script["length_warning"] = f"OVER TARGET: {word_count} words (max {MAX_WORDS}). Trim before recording."

    return script


def _attach_validation(script: dict, topic: dict, result: ValidationResult) -> dict:
    script["validation_score"] = result.score
    script["validation_passed"] = result.passed
    script["validation_errors"] = result.errors
    script["validation_warnings"] = result.warnings
    if not result.passed:
        script["length_warning"] = script.get("length_warning") or result.errors[0]
    return script


def _validation_feedback(result: ValidationResult) -> str:
    lines = ["Fix ALL of the following validation errors:"]
    for err in result.errors:
        lines.append(f"- {err}")
    for warn in result.warnings[:5]:
        lines.append(f"- WARNING: {warn}")
    lines.append(f"Hard max {MAX_WORDS} words. Keep all trigger phrases verbatim in spoken_script.")
    return "\n".join(lines)


async def _voice_rewrite_pass(
    client: anthropic.AsyncAnthropic,
    script: dict,
    topic: dict,
    validation: ValidationResult,
) -> dict | None:
    """Second pass: tighten spoken_script while preserving trigger phrases."""
    triggers = script.get("video_triggers") or {}
    trigger_json = json.dumps(
        {
            "stat_phrases": triggers.get("stat_phrases", []),
            "fun_phrases": triggers.get("fun_phrases", []),
            "beat_phrases": triggers.get("beat_phrases", {}),
            "visual_moments": script.get("visual_moments", []),
        },
        indent=2,
    )
    voice_samples = _load_config_file("voice_samples.txt")
    creator_takes = _load_config_file("creator_takes.txt")
    prompt = (
        "Rewrite ONLY the spoken_script field for a verbatim teleprompter read.\n"
        f"Target: 130-{MAX_WORDS} words. Short punchy sentences. Alternate long and short.\n"
        "Sound like Jugal: third-language clarity, energetic storyteller, not essay.\n"
        "Keep EVERY trigger phrase EXACTLY as listed — do not paraphrase them.\n"
        "Update opening_line, loopback_closer, open_loop_plant, open_loop_payoff to match.\n"
        "Include 1-2 signature phrases from: Right?, That's all it is., The truth is, Figure it out.\n"
        "No banned phrases: here's what's wild, hey guys, I analyzed N posts, interview prep language.\n\n"
        f"VALIDATION ISSUES TO FIX:\n{_validation_feedback(validation)}\n\n"
        f"TRIGGERS (must appear verbatim in spoken_script):\n{trigger_json}\n\n"
        f"VOICE SAMPLES:\n{voice_samples[:2500]}\n\n"
        f"CREATOR VOICE:\n{creator_takes[:1500]}\n\n"
        f"CURRENT spoken_script ({len((script.get('spoken_script') or '').split())} words):\n"
        f"{script.get('spoken_script', '')}\n\n"
        "Return ONLY JSON: {\"spoken_script\", \"opening_line\", \"loopback_closer\", "
        "\"open_loop_plant\", \"open_loop_payoff\"}"
    )
    try:
        response = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        parsed = _parse_script_json(response.content[0].text)
        if not parsed or not parsed.get("spoken_script"):
            return None
        for key in (
            "spoken_script",
            "opening_line",
            "loopback_closer",
            "open_loop_plant",
            "open_loop_payoff",
        ):
            if parsed.get(key):
                script[key] = parsed[key]
        return script
    except Exception as exc:
        print(f"   Voice rewrite failed: {exc}")
        return None


async def _generate_one_script(
    client: anthropic.AsyncAnthropic,
    system_prompt: str,
    topic: dict,
    script_number: int,
    recent_hooks: list[str],
    phase: str,
    brand_episode: int,
    script_type: str,
    batch_size: int,
) -> dict | None:
    """Generate, validate, retry, and voice-rewrite a single script."""
    user_prompt = _build_user_prompt(
        topic, script_number, recent_hooks, phase, brand_episode, script_type, batch_size,
    )
    script: dict | None = None
    last_result: ValidationResult | None = None

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        feedback = ""
        if last_result and not last_result.passed:
            feedback = f"\n\nPREVIOUS ATTEMPT FAILED VALIDATION:\n{_validation_feedback(last_result)}"

        response = await client.messages.create(
            model=SONNET_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt + feedback}],
        )
        script = _parse_script_json(response.content[0].text)
        if not script:
            print(f"   Attempt {attempt}: JSON parse failed")
            continue

        script = _normalize_script(script)
        last_result = validate_script(script, topic)
        script = _attach_validation(script, topic, last_result)

        if last_result.passed:
            print(f"   Validation PASS ({last_result.score}/100) on attempt {attempt}")
            break
        print(f"   Attempt {attempt} FAIL ({last_result.score}/100): {last_result.errors[0]}")

    if not script or not last_result:
        return None

    if not last_result.passed:
        print("   Running voice rewrite pass...")
        rewritten = await _voice_rewrite_pass(client, script, topic, last_result)
        if rewritten:
            script = _normalize_script(rewritten)
            last_result = validate_script(script, topic)
            script = _attach_validation(script, topic, last_result)
            if last_result.passed:
                print(f"   Voice rewrite PASS ({last_result.score}/100)")
            else:
                print(f"   Voice rewrite still FAIL: {last_result.errors[0]}")

    return script


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


def _video_contract_block() -> str:
    contract = _load_config_file("video_contract.txt")
    return (
        "VIDEO-ENGINE CONTRACT (mandatory — video pipeline reads these fields):\n"
        f"{contract}\n\n"
        f"fun_phrases must include 2-3 items from: {FUN_PHRASE_POOL}\n"
        "Each fun_phrase MUST appear verbatim in spoken_script.\n"
        "visual_moments: 2-4 items. stat_phrases: 1-2 items with spoken number phrases.\n"
        "beat_phrases.crust MUST be spoken in the first 15 seconds (e.g. 'step one', 'here's the thing', 'that's not how it works').\n"
        "recording_cues: 5-8 items — teleprompter sheet with second targets, phrases, and actions.\n"
        "edit_template: THREE_STEP_HOT_TAKE for 3-step scripts, CONFESSION_STAT for confession hooks.\n"
    )


def _intro_requirements(brand_episode: int) -> str:
    return (
        f"CONTENT PHASE: INTRO (Brand episode {brand_episode} of 4)\n"
        "This is a brand-building video for a creator just starting out.\n"
        "Goal: build trust AND be reel-energetic — warm but not flat.\n\n"
        "SPOKEN SCRIPT REQUIREMENTS — INTRO MODE:\n"
        "Follow Hook → Problem → Solution → CTA. Include ALL:\n\n"
        "1. HOOK — use ONLY one of these patterns:\n"
        "   - IDENTITY CALL: name exactly who this is for\n"
        "   - CONFESSION: admit something real and specific\n"
        "   - OPEN LOOP: pose a question, answer it later (use sparingly)\n"
        "   Do NOT use CONTRARIAN STRIKE in intro phase.\n"
        "   Prefer opening with a mini-conflict or number, not 'If you've ever wondered...'\n"
        '   NEVER open with "Hey guys", "In this video", or any warmup.\n'
        "   NEVER reuse any opening line from recent_hooks list provided.\n\n"
        "2. OPEN LOOP — plant a soft question in the first 10 seconds.\n"
        "   Resolve it near the end. Keep it personal, not aggressive.\n\n"
        "3. THREE ACTION STEPS — simple and doable. At least one doable TODAY.\n"
        "   Include at least ONE spoken stat (number as words) for stat_phrases.\n\n"
        "4. TONE — warm, honest, peer-to-peer with ONE energy spike mid-script.\n"
        "   Include signature phrase: 'Right?' or 'That's all it is.' or 'The truth is'\n\n"
        "5. LOOP-BACK CLOSER — final line connects back to the opening hook.\n\n"
        "6. LENGTH — HARD MAX 145 words (~50-55 seconds).\n\n"
        "7. VISUAL — populate visual_moments + video_triggers (see contract below).\n\n"
        "8. VALUE FIRST — universal lesson for the viewer. No niche internal work stories.\n\n"
        f'{_video_contract_block()}'
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
        "3. EXACTLY THREE ACTION STEPS — never four or five. Specific, doable THIS WEEK.\n"
        "   At least one real statistic with source named out loud. Not awareness — ACTION.\n\n"
        '4. CASCADING PAYOFFS — each step resolves AND tees up the next\n'
        '   ("that fixes X, but now you have Y — which is step two").\n\n'
        "5. RHYTHM VARIATION — alternate sentence length. Short. Longer. Short.\n\n"
        "6. LOOP-BACK CLOSER — final line connects back to the opening hook.\n\n"
        "7. LENGTH — HARD MAX 145 words (~50-55 seconds). Count before returning.\n"
        "   Short punchy sentences. Cut filler. Every line earns its second.\n"
        "   If draft exceeds 145 words, delete the weakest sentence and tighten.\n\n"
        "8. VISUAL — populate visual_moments (3-5) + video_triggers with broll_phrases "
        "and logo_phrases [{phrase, brand}] when brand tools are named.\n\n"
        "9. VALUE FIRST — 80% of scripts have work_pattern_id: null. No niche internal features.\n"
        "   Optional: ONE generalized credibility line from work_patterns.txt (see TRANSLATION EXAMPLES).\n\n"
        "10. RECORDING CUES — 5-8 teleprompter beats (second, phrase, action).\n"
        "   Include: hook energy, crust pause, stat pauses, step punches, fun phrases, closer.\n\n"
        f'{_video_contract_block()}'
        "- Written in first person, casual, direct\n"
        "- No bullet points in spoken_script — continuous speech\n"
        "- opening_line must match the first sentence of spoken_script exactly\n"
        "- loopback_closer must match the final sentence of spoken_script exactly"
    )


def _resolve_batch_script_types(topics: list[dict]) -> list[str]:
    """Assign NEWS / EVERGREEN / HOT_TAKE mix across a batch."""
    n = len(topics)
    if n == 0:
        return []
    hot_index = next(
        (i for i, t in enumerate(topics) if _script_type_for_topic(t) == "HOT_TAKE"),
        n - 1,
    )
    types: list[str] = []
    for i, topic in enumerate(topics):
        if topic.get("source_type") == "news":
            types.append("NEWS_REACTION")
        elif i == hot_index:
            types.append("HOT_TAKE")
        else:
            types.append("EVERGREEN_VALUE")
    return types


def _build_user_prompt(
    topic: dict,
    script_number: int,
    recent_hooks: list[str],
    phase: str,
    brand_episode: int,
    script_type: str,
    batch_size: int,
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
        f"TERRITORY: {territory}\n"
        f"SOURCE TYPE: {topic.get('source_type', 'trend')}\n\n"
        f"{_script_type_requirements(script_type, script_number, batch_size)}\n"
        f"creator_take_anchor must name the specific POV this script embodies.\n\n"
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

    system_prompt = _build_system_prompt()
    if not system_prompt.strip():
        return []

    phase = phase or get_phase()
    videos_published = get_videos_published()
    print(f"   Phase: {phase.upper()} ({videos_published}/4 videos published)")

    recent_hooks = hook_bank.get_recent_hooks(30)
    if recent_hooks:
        print(f"   Avoiding {len(recent_hooks)} recent hook(s) from hook bank")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    scripts: list[dict] = []
    batch_size = len(topics)
    batch_types = _resolve_batch_script_types(topics)

    for i, topic in enumerate(topics, start=1):
        brand_episode = videos_published + i if phase == "intro" else i
        script_type = batch_types[i - 1]
        print(
            f"   Generating script {i}/{len(topics)} "
            f"[{phase}/{script_type}] {topic['topic_title'][:45]}..."
        )
        try:
            script = await _generate_one_script(
                client,
                system_prompt,
                topic,
                i,
                recent_hooks,
                phase,
                brand_episode,
                script_type,
                batch_size,
            )

            if not script:
                print(f"⚠️ Failed to generate script {i}")
                continue

            script["script_number"] = script.get("script_number", i)
            script["script_type"] = script.get("script_type", script_type)
            script["territory"] = script.get("territory", topic.get("territory", "General"))
            script["source_topic"] = topic["topic_title"]
            script["source_type"] = topic.get("source_type", "trend")
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

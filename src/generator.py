from __future__ import annotations

import json
import os
import re
from pathlib import Path

import anthropic

from src import hook_bank
from src.content_phase import get_phase, get_videos_published
from src.script_validator import ValidationResult, score_story_quality, validate_script

STORY_SCORE_THRESHOLD = 60

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5-20251001"
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
  "script_type": "HACK | TIP | BUILD | ACTIONABLE_NEWS | CONFESSION | STORY_REACTION | HOT_TAKE | EVERGREEN_VALUE",
  "format_hint": "hack | tip | build | news | confession",
  "creator_take_anchor": "one-line POV from creator_takes.txt (opinion angle, not work story)",
  "work_pattern_id": "null or optional id from work_patterns.txt — only if generalized credibility fits",
  "title_overlay": "THE BOLD TITLE IN CAPS",
  "subtitle_overlay": "short descriptive subtitle",
  "spoken_script": "The complete word-for-word script the creator reads...",
  "caption_hook": "One compelling sentence for Instagram/LinkedIn caption",
  "hashtags": ["#Tag1", "#Tag2", "#Tag3", "#Tag4", "#Tag5"],
  "series_note": "Series Title · Ep N/M — stamped by pipeline if missing",
  "series_id": "optional — pipeline may overwrite",
  "recording_tip": "Pause before numbers. First line with energy, not presentation voice. One more specific tip.",
  "hook_type": "IDENTITY CALL | CONFESSION | OPEN LOOP | CONTRARIAN STRIKE",
  "opening_line": "the exact first sentence spoken",
  "open_loop_plant": "the teaser line planted early in the script",
  "open_loop_payoff": "how and where the loop resolves",
  "loopback_closer": "final line that connects back to the hook",
  "visual_cues": "human-readable summary of graphics (legacy, keep for Telegram)",
  "hook_visual": {
    "tier": "higgsfield | fal | remotion",
    "kind": "image_or_short_clip",
    "prompt": "9:16 scroll-stopping proof of the hack — show tool UI or mashup result, not purple AI brains",
    "duration_s": 2.5,
    "why": "prove the tip in the first 2 seconds"
  },
  "visual_briefs": [
    {"tier": "fal", "at_phrase": "exact spoken phrase", "prompt": "specific topical still"},
    {"tier": "remotion", "type": "stat", "display": "$47", "label": "TOKEN BILL"}
  ],
  "visual_moments": [
    {"at_phrase": "exact spoken phrase", "graphic": "23", "label": "LABEL CAPS", "type": "stat", "side": "right"},
    {"at_phrase": "sixty billion dollars", "type": "headline", "source": "FORBES", "headline": "SPACEX ACQUIRES CURSOR FOR $60B", "subheadline": "Deal reshapes AI tooling"},
    {"at_phrase": "recruiters keep saying", "type": "tweet", "handle": "@techcrunch", "display_name": "TechCrunch", "text": "The hiring bar just moved again."},
    {"at_phrase": "my manager texted", "type": "chat", "platform": "imessage", "messages": [{"sender": "them", "text": "Can you ship this tonight?"}, {"sender": "me", "text": "Already done."}]},
    {"at_phrase": "that is wild", "type": "reaction", "emoji": "🤯", "label": "NO WAY"}
  ],
  "video_triggers": {
    "stat_phrases": [{"phrase": "twenty three workflows", "display": "23", "label": "AUTOMATED WORKFLOWS"}],
    "fun_phrases": ["that's normal", "pure building"],
    "energy_words": ["right", "truth"],
    "broll_phrases": ["cursor agent", "claude code terminal"],
    "broll_image_descriptions": ["Cursor IDE agent panel with code diff", "Claude Code terminal with MCP tool call"],
    "beat_phrases": {"crust": "pure building", "payoff": "here's what makes it worth it"}
  },
  "edit_template": "THREE_STEP_HOT_TAKE or CONFESSION_STAT",
  "recording_cues": [
    {"second": 0, "action": "HOOK — lean in, fast, confident. No smile warmup."},
    {"second": 5, "phrase": "here's what's wild", "action": "PAUSE 0.3s then ENERGY UP — crust zoom fires"},
    {"second": 12, "phrase": "forty seven dollars", "action": "PAUSE before number, speak clearly"},
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
        _load_config_file("story_examples.txt"),
    ]
    combined = "\n\n---\n\n".join(p for p in parts if p.strip())
    if not combined.strip():
        print("❌ voice_profile.txt missing — cannot generate scripts")
    return combined


def _script_type_for_topic(topic: dict) -> str:
    hint = (topic.get("format_hint") or topic.get("source_type") or "tip").lower()
    mapping = {
        "hack": "HACK",
        "tip": "TIP",
        "build": "BUILD",
        "news": "ACTIONABLE_NEWS",
        "confession": "CONFESSION",
        "social": "HACK",
        "story": "CONFESSION",
        "trend": "TIP",
    }
    if hint in mapping:
        return mapping[hint]
    title = f"{topic.get('topic_title', '')} {topic.get('topic_summary', '')}".lower()
    if any(kw in title for kw in ("wrong", "myth", "overhyped", "hate", "stop", "don't")):
        return "HOT_TAKE"
    if any(kw in title for kw in ("hack", "mcp", "higgsfield", "mashup")):
        return "HACK"
    if any(kw in title for kw in ("token", "overspend", "bill", "cost")):
        return "CONFESSION"
    return "TIP"


def _story_context_block(topic: dict) -> str:
    """Format Perplexity story seed fields for the generator prompt."""
    parts = []
    for key, label in (
        ("story_hook", "STORY HOOK"),
        ("protagonist", "PROTAGONIST"),
        ("tension", "TENSION"),
        ("payoff", "PAYOFF"),
    ):
        value = (topic.get(key) or "").strip()
        if value:
            parts.append(f"{label}: {value}")
    if not parts:
        return ""
    return "STORY SEED (use as narrative spine — do not turn into a listicle):\n" + "\n".join(parts) + "\n\n"


def _script_type_requirements(script_type: str, script_number: int, batch_size: int) -> str:
    if script_type == "HACK":
        return (
            "SCRIPT TYPE: HACK\n"
            "- Hook names tool A + tool B (or one sharp tool move)\n"
            "- Middle = exact setup the viewer copies today\n"
            "- End = visible outcome / receipt\n"
            "- Prefer hook_type OPEN LOOP or CONFESSION\n"
            "- edit_template: CONFESSION_STAT or THREE_STEP_HOT_TAKE\n"
            "- hook_visual.tier: higgsfield when the hack produces a visual; else fal\n"
        )
    if script_type == "TIP":
        return (
            "SCRIPT TYPE: TIP\n"
            "- One setting, shortcut, rule file, or prompt pattern\n"
            "- No three-step career advice\n"
            "- Receipt: time saved or error avoided\n"
            "- hook_visual.tier: fal\n"
        )
    if script_type == "BUILD":
        return (
            "SCRIPT TYPE: BUILD\n"
            "- Micro ship story — what you made, with which stack\n"
            "- One constraint that forced shipping\n"
            "- Prefer hook_type CONFESSION\n"
        )
    if script_type == "ACTIONABLE_NEWS":
        return (
            "SCRIPT TYPE: ACTIONABLE_NEWS\n"
            "- Changelog or viral thread is backdrop\n"
            "- End with 'do this today' — one feature to try\n"
            "- Include one headline visual_moment if a real source exists\n"
        )
    if script_type == "CONFESSION":
        return (
            "SCRIPT TYPE: CONFESSION\n"
            "- Admit a real fail: tokens, vibe theater, agent thrash\n"
            "- Land the fix with a named tool move\n"
            "- hook_type: CONFESSION; edit_template: CONFESSION_STAT\n"
        )
    if script_type == "STORY_REACTION":
        return (
            "SCRIPT TYPE: STORY_REACTION\n"
            "- Hook = human moment — NOT a press-release headline\n"
            "- Prefer tip/hack energy inside the story\n"
            "- Prefer hook_type CONFESSION or OPEN LOOP\n"
        )
    if script_type == "NEWS_REACTION":
        return (
            "SCRIPT TYPE: NEWS_REACTION — treat as ACTIONABLE_NEWS\n"
            "- Human angle + one action today\n"
        )
    if script_type == "HOT_TAKE":
        return (
            "SCRIPT TYPE: HOT_TAKE\n"
            "- Contrarian but specific to AI coding tools\n"
            "- One concrete alternative workflow\n"
        )
    return (
        "SCRIPT TYPE: EVERGREEN_VALUE — reframed as a tip/hack\n"
        "- Named tools + one copyable move + receipt\n"
        f"- Script {script_number}/{batch_size} in this batch\n"
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
    triggers.setdefault("energy_words", ["right", "truth", "wrong", "secret"])
    triggers.setdefault("broll_phrases", [])
    triggers.setdefault("logo_phrases", [])
    fun = triggers.get("fun_phrases")
    if not isinstance(fun, list) or len(fun) < 2:
        spoken_l = (script.get("spoken_script") or "").lower()
        pool = [p.strip() for p in FUN_PHRASE_POOL.split(",")]
        found = [p for p in pool if p.lower() in spoken_l]
        while len(found) < 2:
            for p in ("wrong", "truth", "insane", "wild", "finally"):
                if p not in found:
                    found.append(p)
                if len(found) >= 2:
                    break
        triggers["fun_phrases"] = found[:3]
    beats = triggers.get("beat_phrases") or {}
    if not isinstance(beats, dict):
        beats = {}
    if not beats.get("crust"):
        spoken = script.get("spoken_script") or ""
        for candidate in ("here's the thing", "that's wrong", "one fix", "the move is", "listen"):
            if candidate in spoken.lower():
                beats["crust"] = candidate
                break
        else:
            beats["crust"] = "here's the thing"
    triggers["beat_phrases"] = beats
    # Ensure first broll layout is immersive for hook punch when layouts missing
    layouts = triggers.get("broll_layouts")
    phrases = triggers.get("broll_phrases") or []
    if phrases and (not isinstance(layouts, list) or len(layouts) < len(phrases)):
        layouts = list(layouts) if isinstance(layouts, list) else []
        while len(layouts) < len(phrases):
            layouts.append("presenter_on_bg" if layouts else "immersive_flash")
        if layouts:
            layouts[0] = "immersive_flash"
        triggers["broll_layouts"] = layouts
    script["video_triggers"] = triggers

    moments = script.get("visual_moments")
    if not isinstance(moments, list):
        script["visual_moments"] = []

    st = (script.get("script_type") or script.get("format_hint") or "").upper()
    title = script.get("title_overlay") or script.get("source_topic") or "AI coding tip"
    default_tier = "higgsfield" if st == "HACK" else "fal"
    if not isinstance(script.get("hook_visual"), dict):
        script["hook_visual"] = {
            "tier": default_tier,
            "kind": "image_or_short_clip",
            "prompt": (
                f"9:16 vertical still proving the tip: {title}. "
                "Show Cursor or Claude Code UI or mashup result. No purple AI brains."
            ),
            "duration_s": 2.5,
            "why": "scroll-stopping proof in first 2 seconds",
        }
    else:
        hv = script["hook_visual"]
        if st == "HACK" and (hv.get("tier") or "").lower() != "higgsfield":
            hv["tier"] = "higgsfield"
        hv.setdefault("duration_s", 2.5)
        hv.setdefault("kind", "image_or_short_clip")
        if not (hv.get("prompt") or "").strip():
            hv["prompt"] = (
                f"9:16 vertical still proving the tip: {title}. "
                "Show tool UI or mashup result. No purple AI brains."
            )
    if not isinstance(script.get("visual_briefs"), list):
        script["visual_briefs"] = []

    hook = script.get("hook_type", "OPEN LOOP")
    script.setdefault("edit_template", HOOK_TO_TEMPLATE.get(hook, "THREE_STEP_HOT_TAKE"))
    if st:
        script.setdefault("format_hint", st.lower() if st != "ACTIONABLE_NEWS" else "news")

    cues = script.get("recording_cues")
    if not isinstance(cues, list) or len(cues) < 4:
        script["recording_cues"] = _build_recording_cues(script)

    num = script.get("script_number", 1)
    title_overlay = script.get("title_overlay", "video")
    script["filename_hint"] = f"script_{int(num):02d}_{_slug_words(title_overlay)}.mp4"

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
    force_story_archetype: str | None = None,
    story_retry_done: bool = False,
) -> dict | None:
    """Generate, validate, retry, and voice-rewrite a single script."""
    user_prompt = _build_user_prompt(
        topic, script_number, recent_hooks, phase, brand_episode, script_type, batch_size,
    )
    if force_story_archetype:
        user_prompt += (
            f"\n\nRETRY — previous draft was too bland/listicle-like.\n"
            f"Force archetype: {force_story_archetype}. Open with CONFESSION or a specific human moment.\n"
            "Weave actions into the story. No consecutive Step one/two/three openers.\n"
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

        story_score = score_story_quality(script, topic)
        script["story_score"] = story_score
        needs_story = (
            script_type in ("STORY_REACTION", "NEWS_REACTION", "EVERGREEN_VALUE")
            and topic.get("source_type") != "journal"
            and story_score < STORY_SCORE_THRESHOLD
            and not story_retry_done
        )
        if needs_story:
            print(f"   Story score {story_score}/100 too low — retrying with confession archetype")
            return await _generate_one_script(
                client,
                system_prompt,
                topic,
                script_number,
                recent_hooks,
                phase,
                brand_episode,
                script_type,
                batch_size,
                force_story_archetype="confession",
                story_retry_done=True,
            )

        if last_result.passed:
            print(f"   Validation PASS ({last_result.score}/100, story {story_score}/100) on attempt {attempt}")
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


async def _extract_visual_requests(
    client: anthropic.AsyncAnthropic,
    raw_transcript: str,
) -> list[dict]:
    """Extract explicit visual/diagram requests from journal ramble via Haiku."""
    if not raw_transcript.strip():
        return []
    prompt = (
        "Extract any explicit visual or diagram requests from this creator transcript.\n"
        "Look for phrases like 'show a diagram of X', 'put up a before/after of Y', "
        "'display the architecture here', 'visualize this'.\n\n"
        f"TRANSCRIPT:\n{raw_transcript}\n\n"
        'Return ONLY a JSON array: [{"trigger_phrase": "exact spoken phrase", '
        '"description": "what visual to show"}] or [] if none.'
    )
    try:
        response = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        match = re.search(r"\[[\s\S]*\]", content)
        if not match:
            return []
        parsed = json.loads(match.group())
        if not isinstance(parsed, list):
            return []
        results = []
        for item in parsed:
            if isinstance(item, dict) and item.get("trigger_phrase"):
                results.append({
                    "trigger_phrase": item["trigger_phrase"],
                    "description": item.get("description", ""),
                    "asset_status": "needs_creation",
                })
        return results
    except Exception as exc:
        print(f"   ⚠️ Visual request extraction failed: {exc}")
        return []


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
        "visual_moments: 2-4 items (stat/step required). Optional 0-2 viral formats: "
        "type tweet|headline|chat|reaction with exact at_phrase in spoken_script.\n"
        "stat_phrases: 1-2 items with spoken number phrases.\n"
        "broll_image_descriptions: REQUIRED when broll_phrases present — same array length. "
        "Specific topical scene per phrase (product UI, metaphor, diagram — not generic stock). "
        "broll_layouts: optional parallel array — presenter_on_bg (default), presenter_cutout (hook hero), immersive_flash (0.5s punch-in).\n"
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
        "CONTENT PHASE: GROWTH — VIBE CODING / NEVER BORING\n"
        "Weekly tips, hacks, builds, actionable news. Viewer acts in ≤10 minutes.\n\n"
        "SPOKEN SCRIPT REQUIREMENTS (ViralTasteGate — hard fail if missing):\n"
        "1. HOOK — named TOOL in the first sentence. NOT 'N points on Hacker News'.\n"
        "   Patterns: CONFESSION | OPEN LOOP | CONTRARIAN STRIKE | IDENTITY CALL\n"
        '   NEVER open with "Hey guys", "In this video", or hiring listicles.\n'
        "   NEVER reuse any opening line from recent_hooks list provided.\n\n"
        "2. ONE COPYABLE MOVE — command, setting, MCP wire, slash command, --model flag.\n"
        "   Prefer ONE hard tip/hack. Max two steps if needed — never Step one/two/three spam.\n"
        "3. RECEIPT — $, minutes saved, file created, ship, or 'do this today'.\n"
        "4. FORMAT — script_type + format_hint must match assigned type for this slot.\n"
        "5. OPEN LOOP — soft unresolved beat early; resolve near the end.\n"
        "6. LENGTH — HARD MAX 145 words.\n"
        "7. VISUAL — hook_visual REQUIRED. HACK → tier higgsfield. TIP/BUILD → fal OK.\n"
        "   Prompt must show tool UI / mashup result — no purple AI brains.\n"
        "   visual_briefs 1-3. visual_moments 3-5. Max ONE higgsfield asset.\n"
        "8. PUNCH PACK — ≥2 fun_phrases from pool verbatim; beat_phrases.crust in first 15s;\n"
        "   energy_words; optional early headline/tweet visual_moment for news/hack.\n"
        "9. Rotate signatures — do NOT default every closer to 'that's all it is.'\n"
        "10. RECORDING CUES — 5-8 teleprompter beats.\n\n"
        f'{_video_contract_block()}'
        "- Written in first person, casual, direct\n"
        "- No bullet points in spoken_script — continuous speech\n"
        "- opening_line must match the first sentence of spoken_script exactly\n"
        "- loopback_closer must match the final sentence of spoken_script exactly"
    )


FORMAT_MIX_ORDER = [
    "HACK",
    "HACK",
    "HACK",
    "TIP",
    "TIP",
    "BUILD",
    "ACTIONABLE_NEWS",
    "CONFESSION",
]


def _resolve_batch_script_types(topics: list[dict]) -> list[str]:
    """Assign weekly format mix across the batch (journal keeps inferred type)."""
    n = len(topics)
    if n == 0:
        return []
    mix = (FORMAT_MIX_ORDER * ((n // len(FORMAT_MIX_ORDER)) + 1))[:n]
    types: list[str] = []
    for i, topic in enumerate(topics):
        if topic.get("source_type") == "journal":
            types.append(_script_type_for_topic(topic))
        else:
            # Prefer mix slot; allow topic hint to swap within similar buckets
            assigned = mix[i]
            hinted = _script_type_for_topic(topic)
            if hinted == assigned:
                types.append(assigned)
            elif assigned == "ACTIONABLE_NEWS" and hinted in ("ACTIONABLE_NEWS", "HOT_TAKE"):
                types.append(hinted)
            else:
                types.append(assigned)
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

    if topic.get("source_type") == "journal":
        raw_transcript = topic.get("raw_transcript", topic.get("topic_summary", ""))
        enrichment = topic.get("journal_enrichment") or {}
        enrich_block = ""
        if enrichment.get("timely_context"):
            hooks = enrichment.get("hook_angles") or []
            stats = enrichment.get("stats_to_weave") or []
            enrich_block = (
                "TIMELY NEWS CONTEXT (from research — weave lightly, do not override the ramble):\n"
                f"{enrichment['timely_context']}\n"
            )
            if hooks:
                enrich_block += f"Optional hook angles: {json.dumps(hooks)}\n"
            if stats:
                enrich_block += (
                    "Verifiable stats you MAY cite if they fit naturally: "
                    f"{json.dumps(stats)}\n"
                )
            enrich_block += (
                "Use this only to sharpen hooks or cite one timely stat — "
                "the creator's ramble remains the primary story.\n\n"
            )
        return (
            "Generate a complete video script FROM the creator's verbatim journal ramble below.\n"
            "Preserve his angle, specifics, and framing — do not genericize into a trend piece.\n"
            "Apply Hook → Problem → Solution → CTA structure on top of HIS words and ideas.\n\n"
            f"CREATOR RAMBLE (verbatim — primary source material):\n{raw_transcript}\n\n"
            f"{enrich_block}"
            f"TERRITORY: {territory}\n"
            f"DOMAIN TAGS: {', '.join(topic.get('domain_tags', []))}\n\n"
            f"{_script_type_requirements(script_type, script_number, batch_size)}\n"
            f"creator_take_anchor must reflect the creator's actual angle from the ramble.\n\n"
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

    return (
        f"Generate a complete video script for the following topic:\n"
        f"TOPIC: {topic['topic_title']}\n"
        f"CONTEXT: {topic.get('topic_summary', '')}\n"
        f"TERRITORY: {territory}\n"
        f"SOURCE TYPE: {topic.get('source_type', 'trend')}\n\n"
        f"{_story_context_block(topic)}"
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
            script["source"] = "journal" if topic.get("source_type") == "journal" else "trending"
            script["custom_visual_overrides"] = []
            if topic.get("queue_id"):
                script["queue_id"] = topic["queue_id"]
            if topic.get("source_type") == "journal":
                raw = topic.get("raw_transcript", "")
                overrides = await _extract_visual_requests(client, raw)
                script["custom_visual_overrides"] = overrides
                if overrides:
                    print(f"   Found {len(overrides)} custom visual request(s)")
                    from src.matcher import update_queue_visual_requests
                    update_queue_visual_requests(topic.get("queue_id", ""), overrides)
            script["content_phase"] = phase
            if phase == "intro":
                script["brand_episode"] = f"{brand_episode} of 4"
            if topic.get("source_url"):
                script["source_url"] = topic["source_url"]
            if topic.get("source_platform"):
                script["source_platform"] = topic["source_platform"]
            if topic.get("format_hint"):
                script.setdefault("format_hint", topic["format_hint"])
            scripts.append(script)

        except Exception as exc:
            print(f"⚠️ Script generation failed for topic {i}: {exc}")
            continue

    if scripts:
        from src.series_calendar import (
            get_active_series,
            increment_episodes_completed,
            stamp_script_series,
        )

        series = get_active_series()
        start_ep = int((series or {}).get("episodes_completed") or 0) + 1
        for idx, script in enumerate(scripts):
            if script.get("source") != "journal" or not script.get("series_note"):
                stamp_script_series(script, start_ep + idx, series)
        if series:
            increment_episodes_completed(len(scripts))
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

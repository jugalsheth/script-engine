from __future__ import annotations

import html
import os
import re
from datetime import datetime
from pathlib import Path

import httpx

TELEGRAM_MAX_LENGTH = 4096


def get_delivery_mode() -> str:
    """Return 'minimal' (default) or 'full' from TELEGRAM_DELIVERY env."""
    mode = os.getenv("TELEGRAM_DELIVERY", "minimal").strip().lower()
    return mode if mode in ("minimal", "full") else "minimal"


def _escape(text: str) -> str:
    return html.escape(str(text))


def _format_hashtags(hashtags: list | str) -> str:
    if isinstance(hashtags, list):
        return " ".join(str(tag) for tag in hashtags)
    return str(hashtags)


def _format_spoken_readable(spoken: str) -> str:
    """One sentence per line for easier reading in Telegram."""
    text = spoken.strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return "\n".join(_escape(p.strip()) for p in parts if p.strip())


def _format_minimal_script(script: dict) -> str:
    number = script.get("script_number", "?")
    territory = _escape(script.get("territory", "General"))
    hook_type = _escape(script.get("hook_type", ""))
    title = _escape(script.get("title_overlay", ""))
    spoken = _format_spoken_readable(script.get("spoken_script", ""))
    filename = _escape(script.get("filename_hint", "script_XX_topic.mp4"))
    est_sec = script.get("estimated_seconds", "?")

    hook_suffix = f" · {hook_type}" if hook_type else ""
    lines = [
        f"<b>SCRIPT {number}</b> · {territory}{hook_suffix}",
        f"<b>{title}</b>",
        "",
        spoken,
        "",
        f"📁 <code>{filename}</code> · ~{est_sec}s",
    ]
    return "\n".join(lines)


def _batch_mix_counts(scripts: list[dict]) -> tuple[int, int, int, int]:
    personal = sum(1 for s in scripts if s.get("source_type") == "journal")
    story = sum(
        1 for s in scripts
        if s.get("source_type") == "story" and s.get("source") != "journal"
    )
    news = sum(
        1 for s in scripts
        if s.get("source_type") == "news" and s.get("source") != "journal"
    )
    evergreen = len(scripts) - personal - story - news
    return personal, story, news, evergreen


def _format_minimal_header(scripts: list[dict], date_str: str) -> str:
    count = len(scripts)
    personal, story, news, evergreen = _batch_mix_counts(scripts)
    return (
        f"🎬 <b>{count} scripts</b> · {date_str} · "
        f"{personal} personal · {story} story · {news} news · {evergreen} evergreen"
    )


def _format_recording_sheet(script: dict) -> str:
    cues = script.get("recording_cues") or []
    filename = _escape(script.get("filename_hint", "script_XX_topic.mp4"))
    word_count = script.get("word_count", "?")
    est_sec = script.get("estimated_seconds", "?")
    length_warn = script.get("length_warning")
    template = _escape(script.get("edit_template", "THREE_STEP_HOT_TAKE"))
    validation_score = script.get("validation_score")
    validation_passed = script.get("validation_passed")
    validation_line = ""
    if validation_score is not None:
        status = "✅" if validation_passed else "⚠️"
        validation_line = f"{status} Validation: {validation_score}/100"
        if script.get("validation_errors"):
            validation_line += f" — {_escape(script['validation_errors'][0][:80])}"
    crust = _escape(
        (script.get("video_triggers") or {}).get("beat_phrases", {}).get("crust", "")
    )
    fun = (script.get("video_triggers") or {}).get("fun_phrases") or []
    fun_line = _escape(", ".join(f'"{p}"' for p in fun[:3]))

    lines = [
        "🎬 <b>RECORDING SHEET</b>",
        f"📁 Save as: <code>{filename}</code>",
        f"⏱️ Target: ~{est_sec}s ({word_count} words) | Template: {template}",
    ]
    if validation_line:
        lines.append(validation_line)
    if length_warn:
        lines.append(f"⚠️ {_escape(length_warn)}")

    overrides = script.get("custom_visual_overrides") or []
    needs_creation = [o for o in overrides if o.get("asset_status") == "needs_creation"]
    if needs_creation:
        script_id = Path(script.get("filename_hint", "script_XX_topic.mp4")).stem
        lines.extend(["", "<b>Custom visuals needed:</b>"])
        for ov in needs_creation:
            trigger = _escape(ov.get("trigger_phrase", ""))
            desc = _escape(ov.get("description", ""))
            lines.append(f"• At <b>{trigger}</b> — {desc}")
            lines.append(
                f"  Drop asset in <code>video-engine/raw_videos/custom_assets/{script_id}/</code>"
            )
            lines.append("  Then set asset_status to \"ready\" in scripts_archive.json")

    lines.extend([
        "",
        "<b>Before you hit record:</b>",
        "• Stand close to camera, chest-up framing",
        "• First line = punch, not presentation voice",
        "• Read spoken_script verbatim — ad-lib breaks overlays",
        f"• Crust beat (~5s): say <b>{crust}</b> with energy",
        f"• Hit fun phrases: {fun_line}",
        "",
        "<b>Beat sheet:</b>",
    ])
    for cue in cues[:8]:
        sec = cue.get("second", "?")
        action = _escape(cue.get("action", ""))
        phrase = cue.get("phrase")
        if phrase:
            lines.append(f"  <b>{sec}s</b> [{_escape(phrase)}] — {action}")
        else:
            lines.append(f"  <b>{sec}s</b> — {action}")
    return "\n".join(lines)


def _format_script_block(script: dict) -> str:
    number = script.get("script_number", "?")
    territory = _escape(script.get("territory", "General"))
    hook_type = _escape(script.get("hook_type", "Unknown"))
    phase = script.get("content_phase", "")
    brand_ep = script.get("brand_episode", "")
    phase_tag = ""
    if phase == "intro" and brand_ep:
        phase_tag = f" | 🌱 INTRO {brand_ep}"
    elif phase == "growth":
        phase_tag = " | 🔥 GROWTH"
    series_note = script.get("series_note")
    title = _escape(script.get("title_overlay", ""))
    subtitle = _escape(script.get("subtitle_overlay", ""))
    spoken = _escape(script.get("spoken_script", ""))
    closer = _escape(script.get("loopback_closer", ""))
    caption = _escape(script.get("caption_hook", ""))
    hashtags = _escape(_format_hashtags(script.get("hashtags", [])))
    visual_cues = _escape(script.get("visual_cues", ""))
    delivery_notes = _escape(script.get("delivery_notes", ""))
    retention_notes = _escape(script.get("retention_notes", ""))
    tip = _escape(script.get("recording_tip", ""))

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>SCRIPT {number}</b> — {territory} | {hook_type}{phase_tag}",
    ]
    if series_note and str(series_note).lower() not in ("null", "none", ""):
        lines.append(_escape(series_note))
    lines.extend(
        [
            f"📌 <b>TITLE OVERLAY:</b> {title}",
            f"📝 <b>SUBTITLE:</b> {subtitle}",
            f"🎤 <b>SPOKEN SCRIPT:</b>",
            spoken,
            f"🔁 <b>CLOSER:</b> {closer}",
            f"📱 <b>CAPTION:</b>",
            caption,
            f"🏷️ <b>HASHTAGS:</b> {hashtags}",
            "━━━━━━━━━━━━━━━━━━",
            f"🎨 <b>VISUAL CUES:</b>",
            visual_cues,
            f"🎙️ <b>DELIVERY NOTES:</b>",
            delivery_notes,
            f"📊 <b>RETENTION NOTES:</b>",
            retention_notes,
            f"🎯 <b>RECORDING TIP:</b> {tip}",
        ]
    )
    return "\n".join(lines)


def _format_header(
    script_count: int,
    date_str: str,
    topics_researched: int,
    topics_dropped: int,
    content_phase: str = "growth",
    scripts: list | None = None,
) -> str:
    phase_line = (
        "🌱 <b>INTRO PHASE</b> — brand-building scripts. Record these first.\n"
        if content_phase == "intro"
        else "🔥 <b>GROWTH PHASE</b> — full power scripts. Go hard.\n"
    )
    validation_line = ""
    if scripts:
        passed = sum(1 for s in scripts if s.get("validation_passed"))
        avg_score = round(sum(s.get("validation_score", 0) for s in scripts) / len(scripts))
        validation_line = f"Validation: {passed}/{len(scripts)} passed | avg {avg_score}/100\n"
    return (
        f"🎬 <b>YOUR {script_count} SCRIPTS</b> — {date_str}\n"
        f"{phase_line}"
        f"{validation_line}"
        f"Generated from {topics_researched} topics researched\n"
        f"{topics_dropped} dropped by safety filter\n"
    )


def _format_footer() -> str:
    return (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Pick 3 this week. Record Mon/Wed/Fri.\n"
        "Post same video to Instagram Reels + LinkedIn Video."
    )


def build_telegram_messages(
    scripts: list[dict],
    topics_researched: int = 0,
    topics_dropped: int = 0,
    content_phase: str = "growth",
    *,
    delivery_mode: str | None = None,
) -> list[str]:
    """Build Telegram message bodies without sending (for tests and delivery)."""
    mode = delivery_mode or get_delivery_mode()
    date_str = datetime.now().strftime("%B %d, %Y")

    if not scripts:
        if mode == "minimal":
            return [
                _truncate_if_needed(
                    f"🎬 <b>0 scripts</b> · {date_str}\n"
                    "⚠️ No scripts were generated this run. Check API keys and logs."
                )
            ]
        header = _format_header(0, date_str, topics_researched, topics_dropped, content_phase, scripts)
        return [_truncate_if_needed(f"{header}\n⚠️ No scripts were generated this run.\n{_format_footer()}")]

    if mode == "minimal":
        messages = [_format_minimal_header(scripts, date_str)]
        for script in scripts:
            messages.append(_format_minimal_script(script))
        return messages

    header = _format_header(
        len(scripts), date_str, topics_researched, topics_dropped, content_phase, scripts,
    )
    footer = _format_footer()
    messages = [header.rstrip()]
    for script in scripts:
        messages.append(_format_recording_sheet(script))
        messages.append(_format_script_block(script))
    messages.append(footer)
    return messages


async def _send_telegram_message(
    client: httpx.AsyncClient, token: str, chat_id: str, text: str
) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    response = await client.post(url, json=payload, timeout=30.0)
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result}")


def _truncate_if_needed(message: str) -> str:
    if len(message) <= TELEGRAM_MAX_LENGTH:
        return message
    return message[: TELEGRAM_MAX_LENGTH - 20] + "\n…[truncated]"


async def send_via_telegram(
    scripts: list[dict],
    topics_researched: int,
    topics_dropped: int,
    content_phase: str = "growth",
) -> None:
    """Format and deliver script batch via Telegram bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("❌ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping delivery")
        return

    mode = get_delivery_mode()
    messages = build_telegram_messages(
        scripts, topics_researched, topics_dropped, content_phase, delivery_mode=mode,
    )

    try:
        async with httpx.AsyncClient() as client:
            for i, message in enumerate(messages, start=1):
                message = _truncate_if_needed(message)
                print(f"   Sending Telegram message {i}/{len(messages)} ({mode} mode)...")
                await _send_telegram_message(client, token, chat_id, message)
        print(f"   Delivered {len(messages)} Telegram message(s)")
    except Exception as exc:
        print(f"❌ Telegram delivery failed: {exc}")

"""
Daily journal ingestion: Telegram voice notes → transcript → journal archive + topic queue.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from faster_whisper import WhisperModel

from src.matcher import (
    domain_tags_for_text,
    find_duplicate_queue_entry,
    load_recent_journal_entries,
    queue_entry_from_transcript,
    save_queue,
    _load_queue,
)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "journal_config.json"
DATA_DIR = ROOT / "data"
JOURNAL_DIR = DATA_DIR / "journal"
OFFSET_PATH = DATA_DIR / "telegram_offset.json"

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "max_duration_sec": 300,
            "whisper_model": "base",
            "dedup_lookback_days": 14,
            "keyword_overlap_threshold": 0.6,
        }


def _load_offset() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not OFFSET_PATH.exists():
        OFFSET_PATH.write_text('{"last_update_id": 0}\n', encoding="utf-8")
        return 0
    try:
        data = json.loads(OFFSET_PATH.read_text(encoding="utf-8"))
        return int(data.get("last_update_id", 0))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0


def _save_offset(update_id: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OFFSET_PATH.write_text(
        json.dumps({"last_update_id": update_id}, indent=2) + "\n",
        encoding="utf-8",
    )


def _journal_path_for_now() -> Path:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return JOURNAL_DIR / f"{month}.jsonl"


def _append_journal_line(entry: dict) -> None:
    path = _journal_path_for_now()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _telegram_api(token: str, method: str, **params) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    with httpx.Client(timeout=120.0) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data["result"]


def _download_voice_file(token: str, file_id: str, dest: Path) -> None:
    file_info = _telegram_api(token, "getFile", file_id=file_id)
    file_path = file_info.get("file_path")
    if not file_path:
        raise RuntimeError("Telegram getFile returned no file_path")
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    with httpx.Client(timeout=120.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


def _transcribe_media(media_path: Path, model_name: str) -> str:
    wav_path = media_path.with_suffix(".wav")
    try:
        subprocess.run(
            [
                "ffmpeg", "-i", str(media_path),
                "-ar", "16000", "-ac", "1", "-y", str(wav_path),
            ],
            capture_output=True,
            check=True,
        )
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(wav_path), beam_size=5, vad_filter=True)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text
    finally:
        media_path.unlink(missing_ok=True)
        wav_path.unlink(missing_ok=True)


def _voice_message_from_update(update: dict) -> dict | None:
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return None
    if msg.get("voice"):
        return msg["voice"]
    if msg.get("audio"):
        return msg["audio"]
    if msg.get("video_note"):
        return msg["video_note"]
    return None


def _process_voice_update(
    update: dict,
    token: str,
    chat_id: str,
    config: dict,
    queue: list[dict],
    journal_recent: list[dict],
) -> tuple[dict | None, bool]:
    """Returns (journal_entry, queue_changed)."""
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return None, False

    if str(msg.get("chat", {}).get("id")) != str(chat_id):
        return None, False

    voice = _voice_message_from_update(update)
    if not voice:
        return None, False

    update_id = update["update_id"]
    duration = int(voice.get("duration", 0))
    file_id = voice["file_id"]
    timestamp = datetime.fromtimestamp(
        msg.get("date", 0), tz=timezone.utc,
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    oversized = duration > config.get("max_duration_sec", 300)
    raw_text = ""

    with tempfile.TemporaryDirectory() as tmpdir:
        media_path = Path(tmpdir) / "note.bin"
        _download_voice_file(token, file_id, media_path)
        raw_text = _transcribe_media(media_path, config.get("whisper_model", "base"))

    if not raw_text:
        print(f"   ⚠️ Empty transcript for update {update_id}, skipping queue")

    domain_tags = domain_tags_for_text(raw_text) if raw_text else []
    queue_id = None
    queue_changed = False

    if raw_text and not oversized:
        duplicate = find_duplicate_queue_entry(raw_text, queue, journal_recent)
        if duplicate:
            duplicate.setdefault("related_mentions", []).append({
                "timestamp": timestamp,
                "raw_text": raw_text,
                "telegram_update_id": update_id,
            })
            queue_id = duplicate["id"]
            queue_changed = True
            print(f"   🔗 Merged duplicate into queue entry {queue_id[:8]}...")
        else:
            new_entry = queue_entry_from_transcript(raw_text, timestamp)
            queue.append(new_entry)
            queue_id = new_entry["id"]
            queue_changed = True
            print(f"   ➕ New queue entry {queue_id[:8]}...")

    entry = {
        "timestamp": timestamp,
        "telegram_update_id": update_id,
        "duration_sec": duration,
        "raw_text": raw_text,
        "domain_tags": domain_tags,
        "queue_id": queue_id,
        "oversized": oversized,
    }
    if oversized:
        print(f"   ⚠️ Oversized voice note ({duration}s) — archived only, not queued")
    return entry, queue_changed


def run() -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

    config = _load_config()
    offset = _load_offset()
    print(f"📓 Journal ingest starting — offset {offset}")

    updates = _telegram_api(token, "getUpdates", offset=offset + 1, timeout=30)
    if not updates:
        print("   No new updates from Telegram")
        return {"processed": 0, "queued": 0, "merged": 0, "oversized": 0}

    print(f"   Received {len(updates)} update(s) from Telegram")
    skipped = 0

    queue = _load_queue()
    journal_recent = load_recent_journal_entries()
    queue_changed = False
    max_update_id = offset
    stats = {"processed": 0, "queued": 0, "merged": 0, "oversized": 0}

    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])
        entry, changed = _process_voice_update(
            update, token, chat_id, config, queue, journal_recent,
        )
        if entry is None:
            skipped += 1
            continue
        _append_journal_line(entry)
        stats["processed"] += 1
        if entry.get("oversized"):
            stats["oversized"] += 1
        elif entry.get("queue_id"):
            if changed and any(
                m.get("telegram_update_id") == entry["telegram_update_id"]
                for q in queue
                for m in (q.get("related_mentions") or [])
            ):
                stats["merged"] += 1
            elif changed:
                stats["queued"] += 1
        if changed:
            queue_changed = True
            journal_recent = load_recent_journal_entries()

    if skipped:
        print(f"   Skipped {skipped} non-voice update(s) (text/replies/etc.)")

    if max_update_id > offset:
        _save_offset(max_update_id)

    if queue_changed:
        save_queue(queue)

    print(
        f"✅ Journal ingest done — processed={stats['processed']} "
        f"queued={stats['queued']} merged={stats['merged']} oversized={stats['oversized']}"
    )
    return stats


if __name__ == "__main__":
    run()

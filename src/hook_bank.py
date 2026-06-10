from __future__ import annotations

import json
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HOOK_BANK_PATH = DATA_DIR / "hook_bank.json"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not HOOK_BANK_PATH.exists():
        HOOK_BANK_PATH.write_text("[]\n", encoding="utf-8")


def load_hooks() -> list:
    """Read data/hook_bank.json; create with empty list if missing."""
    _ensure_data_dir()
    try:
        content = HOOK_BANK_PATH.read_text(encoding="utf-8")
        data = json.loads(content)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_hooks(new_scripts: list) -> None:
    """Append new hooks, dedupe by opening_line, write back to disk."""
    _ensure_data_dir()
    existing = load_hooks()
    seen = {h.get("opening_line", "").strip() for h in existing if h.get("opening_line")}
    today = date.today().isoformat()

    for script in new_scripts:
        opening_line = (script.get("opening_line") or "").strip()
        if not opening_line or opening_line in seen:
            continue
        existing.append(
            {
                "opening_line": opening_line,
                "hook_type": script.get("hook_type", ""),
                "date": today,
            }
        )
        seen.add(opening_line)

    HOOK_BANK_PATH.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    print(f"   Hook bank updated ({len(existing)} hooks total)")


def get_recent_hooks(n: int = 30) -> list[str]:
    """Return the last n opening_line strings for deduplication."""
    hooks = load_hooks()
    lines = [h["opening_line"] for h in hooks if h.get("opening_line")]
    return lines[-n:]

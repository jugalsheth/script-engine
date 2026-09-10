from __future__ import annotations

"""
Edit recipes from creator-kb visual corpus.

Picks FACE_HOOK_SCREEN_PROOF / CONFESSION_STAT / WALKTHROUGH from script type.
Used by script-engine generator + edit brief; video-engine has a twin loader.
"""

import json
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
RECIPES_PATH = CONFIG_DIR / "edit_recipes.json"

# Corpus-backed defaults (2026-W31 visual scan)
FORMAT_TO_RECIPE = {
    "HACK": "FACE_HOOK_SCREEN_PROOF",
    "TIP": "FACE_HOOK_SCREEN_PROOF",
    "BUILD": "FACE_HOOK_SCREEN_PROOF",
    "ACTIONABLE_NEWS": "FACE_HOOK_SCREEN_PROOF",
    "NEWS_REACTION": "FACE_HOOK_SCREEN_PROOF",
    "STORY_REACTION": "CONFESSION_STAT",
    "CONFESSION": "CONFESSION_STAT",
    "HOT_TAKE": "FACE_HOOK_SCREEN_PROOF",
}

HOOK_TO_RECIPE = {
    "CONFESSION": "CONFESSION_STAT",
    "OPEN LOOP": "FACE_HOOK_SCREEN_PROOF",
    "OPEN_LOOP": "FACE_HOOK_SCREEN_PROOF",
    "CURIOSITY": "FACE_HOOK_SCREEN_PROOF",
    "PROOF": "FACE_HOOK_SCREEN_PROOF",
    "CONTRARIAN": "FACE_HOOK_SCREEN_PROOF",
    "CONTRARIAN STRIKE": "FACE_HOOK_SCREEN_PROOF",
    "IDENTITY CALL": "FACE_HOOK_SCREEN_PROOF",
    "HOT TAKE": "FACE_HOOK_SCREEN_PROOF",
    "LISTICLE": "WALKTHROUGH",
}

WALKTHROUGH_HINTS = (
    "install",
    "walkthrough",
    "step by step",
    "part ",
    "upload",
    "download",
    "create a new",
    "go to settings",
    "open the",
)

FALLBACK_RECIPES = {
    "FACE_HOOK_SCREEN_PROOF": {
        "id": "FACE_HOOK_SCREEN_PROOF",
        "when": "HACK/TIP with copyable UI move",
        "hook": "Chest-up face + bold top-third hook text for 1.5–2.5s, then hard cut to screen record",
        "mid": "Screen record on the exact settings path; Remotion stat on the receipt number",
        "capture": ["talking_head mp4", "1–2 UI screenshots or 10s screen record"],
        "remotion": ["stat overlay", "reaction at frustration beat", "headline on copyable move"],
    },
    "CONFESSION_STAT": {
        "id": "CONFESSION_STAT",
        "when": "CONFESSION / micro-story with number receipt",
        "hook": "Face close-up, no text first second — emotion sells; stat pops at payoff phrase",
        "mid": "Mostly face; optional single UI screenshot as proof",
        "capture": ["talking_head mp4", "optional one receipt screenshot"],
        "remotion": ["stat at receipt", "reaction at confession beat"],
    },
    "WALKTHROUGH": {
        "id": "WALKTHROUGH",
        "when": "Tool install / step process (Part X series style)",
        "hook": "Face + series hook text box at top; transition to full-screen UI early",
        "mid": "Continuous screen record with minimal face return",
        "capture": ["talking_head 5–8s", "screen record of full flow"],
        "remotion": ["step labels optional — prefer native UI"],
    },
}


def load_recipes_pack() -> dict:
    if not RECIPES_PATH.exists():
        return {
            "version": 0,
            "default_hook_style": "face+text",
            "default_edit_pattern": "face_then_screen",
            "recipes": list(FALLBACK_RECIPES.values()),
            "hook_visual_defaults": {
                "tier": "higgsfield",
                "kind": "image_or_short_clip",
                "duration_s": 2.5,
                "prompt_rules": [
                    "9:16 product UI or terminal — not abstract AI brain",
                    "Name the exact tool (Cursor, Claude Code, etc.)",
                ],
            },
            "anti_patterns": [
                "generic neon AI brain b-roll",
                "rapid montage / jump-cut anxiety",
                "hook unrelated to spoken tip",
            ],
            "taste_tags": [
                "chest_up_talking_head",
                "dark_ui_broll",
                "slow_deliberate_pacing",
                "bottom_safe_text",
            ],
        }
    try:
        return json.loads(RECIPES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "recipes": list(FALLBACK_RECIPES.values()),
            "default_hook_style": "face+text",
            "default_edit_pattern": "face_then_screen",
        }


def recipe_by_id(recipe_id: str, pack: dict | None = None) -> dict:
    pack = pack or load_recipes_pack()
    for r in pack.get("recipes") or []:
        if r.get("id") == recipe_id:
            return r
    return FALLBACK_RECIPES.get(recipe_id) or FALLBACK_RECIPES["FACE_HOOK_SCREEN_PROOF"]


def _looks_like_walkthrough(script: dict) -> bool:
    blob = " ".join(
        str(script.get(k) or "")
        for k in ("spoken_script", "title_overlay", "source_topic", "visual_cues", "format_hint")
    ).lower()
    return any(h in blob for h in WALKTHROUGH_HINTS)


def pick_recipe_id(script: dict) -> str:
    """Choose corpus recipe id for a script. Content beats legacy LLM template names."""
    st = (script.get("script_type") or script.get("format_hint") or "").upper()
    if st in ("ACTIONABLE_NEWS", "NEWS"):
        st = "ACTIONABLE_NEWS"
    hook = (script.get("hook_type") or "").upper().replace("_", " ").strip()

    if st == "CONFESSION" or hook == "CONFESSION":
        return "CONFESSION_STAT"
    if _looks_like_walkthrough(script) and st != "CONFESSION":
        return "WALKTHROUGH"
    if st in FORMAT_TO_RECIPE:
        return FORMAT_TO_RECIPE[st]
    if hook in HOOK_TO_RECIPE:
        return HOOK_TO_RECIPE[hook]

    explicit = (script.get("edit_template") or "").strip().upper()
    if explicit in FALLBACK_RECIPES:
        return explicit
    if explicit == "THREE_STEP_HOT_TAKE":
        return "FACE_HOOK_SCREEN_PROOF"
    return "FACE_HOOK_SCREEN_PROOF"


def apply_recipe_to_script(script: dict) -> dict:
    """Set edit_template + recipe metadata; nudge hook_visual from corpus defaults."""
    pack = load_recipes_pack()
    recipe_id = pick_recipe_id(script)
    recipe = recipe_by_id(recipe_id, pack)
    script["edit_template"] = recipe_id
    script["edit_recipe"] = {
        "id": recipe_id,
        "hook": recipe.get("hook", ""),
        "mid": recipe.get("mid", ""),
        "capture": recipe.get("capture") or [],
        "remotion": recipe.get("remotion") or [],
        "when": recipe.get("when", ""),
    }
    script["edit_pattern"] = pack.get("default_edit_pattern") or "face_then_screen"
    script["hook_style"] = pack.get("default_hook_style") or "face+text"

    defaults = pack.get("hook_visual_defaults") or {}
    hv = script.get("hook_visual")
    if isinstance(hv, dict):
        hv.setdefault("kind", defaults.get("kind") or "image_or_short_clip")
        hv.setdefault("duration_s", defaults.get("duration_s") or 2.5)
        rules = defaults.get("prompt_rules") or []
        prompt = (hv.get("prompt") or "").lower()
        if any(bad in prompt for bad in ("ai brain", "neon network", "futuristic hud", "purple")):
            title = script.get("title_overlay") or script.get("source_topic") or "tool UI"
            hv["prompt"] = (
                f"9:16 vertical product UI proving: {title}. "
                "Dark IDE/terminal or settings panel. No abstract AI brains."
            )
        if rules and "why" not in hv:
            hv["why"] = "corpus default: face+text then UI proof"
        script["hook_visual"] = hv

    return script


def recipe_prompt_block() -> str:
    """Short block for LLM system/user prompts."""
    pack = load_recipes_pack()
    lines = [
        "EDIT RECIPES (from viral visual corpus — pick one via edit_template):",
        f"- Default hook style: {pack.get('default_hook_style', 'face+text')}",
        f"- Default pattern: {pack.get('default_edit_pattern', 'face_then_screen')}",
        "- FACE_HOOK_SCREEN_PROOF — HACK/TIP: face+bold top text ~2s → hard cut to UI proof",
        "- CONFESSION_STAT — confession: face first (emotion), Remotion stat on receipt",
        "- WALKTHROUGH — install/series: short face hook → full-screen screen record",
        "- Prefer real product UI over abstract AI visuals",
        "- Slow pacing, hard cuts only — no jump-cut montages",
    ]
    anti = (pack.get("anti_patterns") or [])[:5]
    for a in anti:
        lines.append(f"- AVOID: {a[:120]}")
    return "\n".join(lines)

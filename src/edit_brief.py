from __future__ import annotations

"""
Edit Brief — least-complicated pre-edit checklist.

Turns a script into: what to record, what screenshots to grab, filenames, drop paths.
Remotion handles stats/reactions/headlines automatically.
"""

import argparse
import json
import re
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ENGINE_ROOT.parent
VIDEO_ENGINE_ROOT = REPO_ROOT / "video-engine"
ARCHIVE_PATH = ENGINE_ROOT / "data" / "scripts_archive.json"

MAX_CAPTURE_ASSETS = 3


def _slugify(name: str) -> str:
    stem = Path(name).stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("_")
    return stem or "untitled"


def project_id_from_script(script: dict) -> str:
    hint = script.get("filename_hint") or f"script_{script.get('script_number', 'unknown')}"
    return _slugify(hint)


def _infer_capture_kind(prompt: str) -> str:
    text = prompt.lower()
    if any(k in text for k in ("screen record", "screen recording", "scrolling", "walkthrough")):
        return "screen_recording"
    if any(k in text for k in ("terminal", "cli", "command line", "output")):
        return "screenshot"
    if any(k in text for k in ("settings", "panel", "tab", "toggle", "editor", "ide", "file explorer")):
        return "screenshot"
    return "screenshot"


def _short_label(prompt: str, max_len: int = 72) -> str:
    text = re.sub(r"\s+", " ", prompt.strip())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _filename_for_capture(project_id: str, index: int, kind: str, phrase: str = "") -> str:
    slug = _slugify(phrase)[:40] if phrase else f"asset_{index:02d}"
    ext = ".mp4" if kind == "screen_recording" else ".png"
    if index == 0 and kind != "screen_recording":
        return f"hook_{slug}{ext}"
    return f"{index:02d}_{slug}{ext}"


def _talking_head_step(script: dict, project_id: str) -> dict:
    filename = script.get("filename_hint") or f"{project_id}.mp4"
    opening = script.get("opening_line") or ""
    if not opening and script.get("spoken_script"):
        opening = script["spoken_script"].split(".")[0].strip() + "."

    return {
        "step": 1,
        "category": "talking_head",
        "required": True,
        "title": "Record your talking-head video",
        "action": "Film chest-up, phone vertical (9:16). Read spoken_script verbatim.",
        "first_line": opening,
        "duration_target": f"~{script.get('estimated_seconds', '?')}s",
        "recording_tip": script.get("recording_tip", ""),
        "filename": filename,
        "drop_paths": [
            f"video-engine/inbox/{filename}",
            f"video-engine/projects/{project_id}/raw.mp4",
        ],
    }


def _capture_from_prompt(
    *,
    index: int,
    project_id: str,
    prompt: str,
    at_phrase: str,
    role: str,
    required: bool,
    why: str = "",
) -> dict:
    kind = _infer_capture_kind(prompt)
    filename = _filename_for_capture(project_id, index, kind, at_phrase or role)
    assets_dir = f"video-engine/projects/{project_id}/assets/"

    if kind == "screen_recording":
        action = f"Screen record: {_short_label(prompt)}"
        how = "10–15s max. Show the UI move clearly — no face, no cursor wandering."
    else:
        action = f"Screenshot: {_short_label(prompt)}"
        how = "PNG or JPG. Crop to 9:16 if needed. Hide personal data."

    return {
        "step": index + 2,
        "category": kind,
        "required": required,
        "title": role,
        "action": action,
        "when_in_script": at_phrase,
        "how": how,
        "filename": filename,
        "drop_path": assets_dir,
        "why": why,
    }


def _collect_capture_steps(script: dict, project_id: str) -> tuple[list[dict], list[str], list[str]]:
    captures: list[dict] = []
    auto_handled: list[str] = []
    skip: list[str] = []
    seen_phrases: set[str] = set()

    overrides = script.get("custom_visual_overrides") or []
    for ov in overrides:
        if ov.get("asset_status") == "ready":
            continue
        trigger = ov.get("trigger_phrase", "")
        if trigger in seen_phrases:
            continue
        seen_phrases.add(trigger)
        captures.append(
            _capture_from_prompt(
                index=len(captures),
                project_id=project_id,
                prompt=ov.get("description") or trigger,
                at_phrase=trigger,
                role="Custom visual (from your journal)",
                required=True,
                why="You asked for this visual when you recorded the journal entry.",
            )
        )

    hook = script.get("hook_visual") or {}
    if isinstance(hook, dict) and hook.get("tier") in ("fal", "higgsfield", "manual"):
        prompt = hook.get("prompt", "")
        if prompt and len(captures) < MAX_CAPTURE_ASSETS:
            captures.append(
                _capture_from_prompt(
                    index=len(captures),
                    project_id=project_id,
                    prompt=prompt,
                    at_phrase=script.get("opening_line", "first 2 seconds"),
                    role="Hook visual (first ~2s before your face)",
                    required=False,
                    why=hook.get("why", "Stops the scroll — proves the problem is real."),
                )
            )
            captures[-1]["optional_alternative"] = (
                f"Or drop a 2–3s clip as hook_hero.mp4 in video-engine/projects/{project_id}/assets/"
            )

    for brief in script.get("visual_briefs") or []:
        if len(captures) >= MAX_CAPTURE_ASSETS:
            break
        tier = brief.get("tier", "")
        if tier == "remotion":
            phrase = brief.get("at_phrase") or brief.get("label") or "on cue"
            label = brief.get("label") or brief.get("display") or brief.get("type", "overlay")
            auto_handled.append(f"{label} overlay at “{phrase}”")
            continue
        if tier != "fal":
            continue
        phrase = brief.get("at_phrase", "")
        if phrase in seen_phrases:
            continue
        seen_phrases.add(phrase)
        captures.append(
            _capture_from_prompt(
                index=len(captures),
                project_id=project_id,
                prompt=brief.get("prompt", phrase),
                at_phrase=phrase,
                role="B-roll proof shot",
                required=False,
                why="Shows the exact UI moment you mention — skip if you want AI-generated B-roll.",
            )
        )

    for moment in script.get("visual_moments") or []:
        mtype = moment.get("type", "")
        phrase = moment.get("at_phrase", "")
        if mtype == "reaction":
            auto_handled.append(f"Reaction at “{phrase}”")
        elif mtype == "stat":
            auto_handled.append(
                f"Stat “{moment.get('graphic', '')}” — {moment.get('label', '')} at “{phrase}”"
            )
        elif mtype == "headline":
            auto_handled.append(f"Headline card at “{phrase}”")
        else:
            auto_handled.append(f"{mtype} overlay at “{phrase}”")

    fal_brief_count = sum(
        1 for b in (script.get("visual_briefs") or []) if b.get("tier") == "fal"
    )
    if fal_brief_count > MAX_CAPTURE_ASSETS:
        skip.append(
            f"{fal_brief_count - MAX_CAPTURE_ASSETS} extra B-roll shot(s) — AI generates if you skip"
        )

    return captures, auto_handled, skip


def build_edit_brief(script: dict) -> dict:
    """Return structured edit brief for one script."""
    project_id = project_id_from_script(script)
    talking_head = _talking_head_step(script, project_id)
    captures, auto_handled, skip = _collect_capture_steps(script, project_id)

    # Align capture guidance with corpus recipe when present
    recipe = script.get("edit_recipe")
    if not recipe:
        try:
            from src.edit_recipes import apply_recipe_to_script, recipe_by_id, pick_recipe_id
            from src.edit_beats import apply_edit_beats

            apply_recipe_to_script(script)
            apply_edit_beats(script)
            recipe = script.get("edit_recipe") or recipe_by_id(pick_recipe_id(script))
        except Exception:
            recipe = None
    else:
        try:
            from src.edit_beats import apply_edit_beats

            if not script.get("edit_beats"):
                apply_edit_beats(script)
        except Exception:
            pass

    if recipe:
        for item in recipe.get("capture") or []:
            low = item.lower()
            if "screen" in low and not any(
                c.get("category") == "screen_recording" for c in captures
            ):
                skip.append(f"Recipe wants: {item}")
            elif "screenshot" in low or "ui" in low:
                if not captures:
                    skip.append(f"Recipe wants: {item}")
        for rem in recipe.get("remotion") or []:
            if rem not in auto_handled:
                auto_handled.append(f"Recipe Remotion: {rem}")

    required_captures = sum(1 for c in captures if c.get("required"))
    optional_captures = len(captures) - required_captures

    return {
        "project_id": project_id,
        "title": script.get("title_overlay", ""),
        "script_number": script.get("script_number"),
        "filename_hint": script.get("filename_hint"),
        "edit_template": script.get("edit_template"),
        "edit_recipe": recipe,
        "edit_beats": script.get("edit_beats"),
        "hook_mode": script.get("hook_mode") or "complementary",
        "talking_head": talking_head,
        "captures": captures,
        "auto_handled": auto_handled,
        "skip_or_optional": skip,
        "summary": {
            "must_record": 1,
            "must_capture": required_captures,
            "nice_to_capture": optional_captures,
            "remotion_handles": len(auto_handled),
        },
        "workflow": [
            "1. Record talking-head → drop in inbox/ or projects/{id}/raw.mp4",
            "2. Grab screenshots (if any) → projects/{id}/assets/",
            "3. Run: cd video-engine && python pipeline.py projects/{id}/raw.mp4",
        ],
    }


def format_edit_brief_markdown(brief: dict) -> str:
    """Human-readable checklist — print or save as EDIT_BRIEF.md."""
    pid = brief["project_id"]
    lines = [
        f"# Edit Brief — {brief.get('title') or pid}",
        "",
        f"**Project folder:** `video-engine/projects/{pid}/`",
    ]
    recipe = brief.get("edit_recipe") or {}
    if recipe.get("id"):
        lines.extend([
            "",
            f"**Edit recipe:** `{recipe['id']}` — {recipe.get('when', '')}",
            f"- Hook: {recipe.get('hook', '')}",
            f"- Mid: {recipe.get('mid', '')}",
        ])
    beats = brief.get("edit_beats") or {}
    triple = (beats.get("hook_triple") or {}) if isinstance(beats, dict) else {}
    if triple.get("written") or triple.get("verbal"):
        lines.extend([
            "",
            "**Triple hook (first ~2.5s):**",
            f"- Verbal: “{(triple.get('verbal') or '')[:90]}”",
            f"- Written title: `{(triple.get('written') or '')}`",
            f"- Visual: drop `{triple.get('visual') or 'hook_hero'}` in assets/ (UI proof, not AI brain)",
            f"- Hook mode: `{brief.get('hook_mode') or 'complementary'}` (complementary ≠ same words; cliff = incomplete title)",
        ])
    if recipe.get("id") == "FACE_HOOK_SCREEN_PROOF":
        lines.append("- Proof screenshot required at the copyable-move beat (full-bleed on screen).")
    lines.extend([
        "",
        "## Before you edit (5 min checklist)",
        "",
    ])

    th = brief["talking_head"]
    lines.extend([
        f"### Step {th['step']}. {th['title']} ✅ REQUIRED",
        "",
        f"- **Do:** {th['action']}",
        f"- **First line:** “{th.get('first_line', '')}”",
        f"- **Length:** {th.get('duration_target', '?')}",
    ])
    if th.get("recording_tip"):
        lines.append(f"- **Tip:** {th['recording_tip']}")
    lines.append(f"- **Save as:** `{th['filename']}`")
    lines.append("- **Drop here (either works):**")
    for p in th["drop_paths"]:
        lines.append(f"  - `{p}`")
    lines.append("")

    if not brief["captures"]:
        lines.extend([
            "### Screenshots / B-roll",
            "",
            "_None required — Remotion overlays handle the edit._",
            "",
        ])
    else:
        lines.append("### Screenshots / screen recordings")
        lines.append("")
        for cap in brief["captures"]:
            tag = "✅ REQUIRED" if cap.get("required") else "○ optional"
            lines.append(f"#### Step {cap['step']}. {cap['title']} ({tag})")
            lines.append("")
            lines.append(f"- **Do:** {cap['action']}")
            if cap.get("when_in_script"):
                lines.append(f"- **When you say:** “{cap['when_in_script']}”")
            lines.append(f"- **How:** {cap['how']}")
            lines.append(f"- **Save as:** `{cap['filename']}`")
            lines.append(f"- **Drop in:** `{cap['drop_path']}`")
            if cap.get("why"):
                lines.append(f"- **Why:** {cap['why']}")
            if cap.get("optional_alternative"):
                lines.append(f"- **Or:** {cap['optional_alternative']}")
            lines.append("")

    if brief["auto_handled"]:
        lines.extend([
            "## Remotion handles automatically (don't record these)",
            "",
        ])
        for item in brief["auto_handled"]:
            lines.append(f"- {item}")
        lines.append("")

    if brief["skip_or_optional"]:
        lines.extend(["## Skip if you're in a hurry", ""])
        for item in brief["skip_or_optional"]:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend([
        "## After capture",
        "",
        "```bash",
        f"cd video-engine",
        f"python pipeline.py projects/{pid}/raw.mp4",
        "```",
        "",
        f"Optional PNGs go in `projects/{pid}/assets/` — matched automatically by filename.",
    ])
    return "\n".join(lines)


def format_edit_brief_telegram(brief: dict) -> str:
    """Compact HTML block for Telegram."""
    pid = brief["project_id"]
    th = brief["talking_head"]
    lines = [
        f"📸 <b>CAPTURE LIST</b> · {brief.get('title', pid)}",
        "",
        f"<b>1. Record</b> → <code>{th['filename']}</code>",
        f"   Drop in <code>inbox/</code> or <code>projects/{pid}/raw.mp4</code>",
    ]
    if th.get("first_line"):
        lines.append(f"   Open: “{th['first_line'][:80]}…”")

    for cap in brief["captures"]:
        req = "✅" if cap.get("required") else "○"
        lines.append("")
        lines.append(f"<b>{cap['step']}. {req} {cap['title']}</b>")
        lines.append(f"   {cap['action'][:100]}")
        lines.append(f"   → <code>{cap['drop_path']}{cap['filename']}</code>")

    if brief["auto_handled"]:
        lines.append("")
        lines.append(f"<b>Auto:</b> {len(brief['auto_handled'])} overlays (stats, reactions, titles)")

    return "\n".join(lines)


def attach_edit_briefs(scripts: list[dict]) -> list[dict]:
    """Add edit_brief field to each script dict (in place)."""
    for script in scripts:
        script["edit_brief"] = build_edit_brief(script)
    return scripts


def _load_script(source: Path, script_number: int | None) -> dict:
    data = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        scripts = [data]
    else:
        scripts = data

    if script_number is not None:
        for s in scripts:
            if s.get("script_number") == script_number:
                return s
        raise SystemExit(f"No script_number={script_number} in {source}")

    if len(scripts) == 1:
        return scripts[0]
    raise SystemExit(f"{source} has {len(scripts)} scripts — pass --number N")


def write_edit_brief_file(brief: dict) -> Path:
    pid = brief["project_id"]
    out_dir = VIDEO_ENGINE_ROOT / "projects" / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "EDIT_BRIEF.md"
    out_path.write_text(format_edit_brief_markdown(brief), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a capture checklist for a script (what to record / screenshot)"
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=ARCHIVE_PATH,
        help="JSON file with script(s) (default: data/scripts_archive.json)",
    )
    parser.add_argument("--number", type=int, help="script_number to use")
    parser.add_argument("--write", action="store_true", help="Write EDIT_BRIEF.md to video-engine/projects/")
    parser.add_argument("--json", action="store_true", help="Print structured JSON")
    args = parser.parse_args()

    if not args.file.exists():
        raise SystemExit(f"File not found: {args.file}")

    script = _load_script(args.file, args.number)
    brief = build_edit_brief(script)

    if args.write:
        path = write_edit_brief_file(brief)
        print(f"Wrote {path}")

    if args.json:
        print(json.dumps(brief, indent=2))
    elif not args.write:
        print(format_edit_brief_markdown(brief))
    elif not args.json:
        print(format_edit_brief_markdown(brief))


if __name__ == "__main__":
    main()

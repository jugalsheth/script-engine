from __future__ import annotations

"""Derive edit_beats so video-engine can enforce script craft visually."""


def _first_stat_phrase(script: dict) -> str:
    for m in script.get("visual_moments") or []:
        if isinstance(m, dict) and m.get("type") == "stat" and m.get("at_phrase"):
            return str(m["at_phrase"])
    for sp in (script.get("video_triggers") or {}).get("stat_phrases") or []:
        if isinstance(sp, dict) and sp.get("phrase"):
            return str(sp["phrase"])
        if isinstance(sp, str):
            return sp
    return ""


def _first_fal_or_ui_phrase(script: dict) -> str:
    for b in script.get("visual_briefs") or []:
        if isinstance(b, dict) and b.get("tier") in ("fal", "manual") and b.get("at_phrase"):
            return str(b["at_phrase"])
    for ov in script.get("custom_visual_overrides") or []:
        if isinstance(ov, dict) and ov.get("trigger_phrase"):
            return str(ov["trigger_phrase"])
    phrases = (script.get("video_triggers") or {}).get("broll_phrases") or []
    if phrases:
        return str(phrases[0] if isinstance(phrases[0], str) else phrases[0].get("phrase", ""))
    return ""


def _struggle_phrase(script: dict) -> str:
    spoken = (script.get("spoken_script") or "").lower()
    for cue in (
        "that's insane",
        "truth is",
        "i thought",
        "wrong",
        "wasted",
        "burned",
        "failing",
        "nightmare",
        "no idea",
    ):
        if cue in spoken:
            # return a short slice from spoken for matching
            idx = spoken.find(cue)
            return (script.get("spoken_script") or "")[idx : idx + len(cue) + 20].split(".")[0]
    for m in script.get("visual_moments") or []:
        if isinstance(m, dict) and m.get("type") == "reaction" and m.get("at_phrase"):
            return str(m["at_phrase"])
    return ""


def derive_edit_beats(script: dict) -> dict:
    """Build edit_beats from existing script fields (idempotent)."""
    existing = script.get("edit_beats")
    if isinstance(existing, dict) and existing.get("hook_triple"):
        return existing

    opening = script.get("opening_line") or ""
    if not opening and script.get("spoken_script"):
        opening = script["spoken_script"].split(".")[0].strip() + "."

    written = script.get("title_overlay") or ""
    hv = script.get("hook_visual") if isinstance(script.get("hook_visual"), dict) else {}
    visual = "hook_hero"
    if hv.get("asset_file"):
        visual = str(hv["asset_file"])
    elif hv.get("tier"):
        visual = "hook_hero"

    rehook = (
        script.get("open_loop_plant")
        or (script.get("video_triggers") or {}).get("beat_phrases", {}).get("crust")
        or "here's the thing"
    )
    proof = _first_fal_or_ui_phrase(script) or rehook
    receipt = (
        (script.get("video_triggers") or {}).get("beat_phrases", {}).get("payoff")
        or _first_stat_phrase(script)
        or script.get("open_loop_payoff")
        or ""
    )
    struggle = _struggle_phrase(script)
    closer = script.get("loopback_closer") or ""

    return {
        "hook_triple": {
            "verbal": opening,
            "written": written,
            "visual": visual,
        },
        "rehook_at": rehook if isinstance(rehook, str) else str(rehook),
        "struggle_at": struggle,
        "proof_at": proof,
        "receipt_at": receipt if isinstance(receipt, str) else str(receipt),
        "closer_at": closer,
        "recipe_id": (script.get("edit_recipe") or {}).get("id")
        or script.get("edit_template")
        or "FACE_HOOK_SCREEN_PROOF",
    }


def apply_edit_beats(script: dict) -> dict:
    script["edit_beats"] = derive_edit_beats(script)
    return script

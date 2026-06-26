from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
ARCHIVE_PATH = Path(__file__).resolve().parent.parent / "data" / "scripts_archive.json"

MAX_WORDS = 145
MAX_AVG_SENTENCE_WORDS = 18
MAX_SENTENCE_WORDS = 25
MIN_SIGNATURE_PHRASES = 1
MAX_SIGNATURE_PHRASES = 2

SIGNATURE_PHRASES = [
    "right?",
    "unless and until",
    "that's all it is",
    "at the end of the day",
    "that's that",
    "figure it out",
    "that's not how it works in production",
    "the truth is",
    "get shit done",
]

FAKE_STAT_PATTERNS = [
    r"according to (?:the )?(?:bureau of labor|stack overflow|github developer survey)",
    r"this week'?s (?:jobs report|hiring report|hiring data)",
    r"according to this week",
]

EXPERIENCE_FRAMING = [
    "teams i work with",
    "in production",
    "what i see",
    "what we see",
    "engineers i know",
]

EMOTION_WORDS = [
    "betrayed", "relieved", "stunned", "frustrated", "shocked", "surprised",
    "panicked", "excited", "worried", "proud", "embarrassed", "grateful",
]

LISTICLE_STEP_PATTERN = re.compile(
    r"step\s+(?:one|two|three|1|2|3)\b",
    re.I,
)

NEWSINESS_PATTERN = re.compile(
    r"according to (?:this week|the latest|a report)",
    re.I,
)

STORY_SCORE_THRESHOLD = 60


def score_story_quality(script: dict, topic: dict | None = None) -> int:
    """Score 0-100 for narrative richness (higher = more story-like)."""
    spoken = (script.get("spoken_script") or "").strip()
    if not spoken:
        return 0

    score = 50
    spoken_lower = spoken.lower()
    source = (topic or {}).get("source_type", "")
    script_type = script.get("script_type", "")

    if source == "journal":
        return 100

    hook_type = (script.get("hook_type") or "").upper()
    if hook_type in ("CONFESSION", "OPEN LOOP"):
        score += 15

    if any(word in spoken_lower for word in EMOTION_WORDS):
        score += 12

    sentences = _sentences(spoken)
    step_opener_count = sum(
        1 for s in sentences[:6]
        if LISTICLE_STEP_PATTERN.match(s.strip())
    )
    if step_opener_count >= 3:
        score -= 25
    elif step_opener_count >= 2:
        score -= 12

    if NEWSINESS_PATTERN.search(spoken_lower):
        first_third = spoken_lower[: max(1, len(spoken_lower) // 3)]
        has_human_open = any(
            w in first_third
            for w in ("i ", "my ", "we ", "felt", "turns out", "wrong", "failed")
        )
        if not has_human_open:
            score -= 15

    if topic and (topic.get("story_hook") or topic.get("tension")):
        story_terms = " ".join(
            filter(None, [
                topic.get("story_hook", ""),
                topic.get("tension", ""),
                topic.get("payoff", ""),
            ])
        ).lower()
        if any(term in spoken_lower for term in story_terms.split() if len(term) > 5):
            score += 8

    if script_type in ("STORY_REACTION", "NEWS_REACTION") and len(sentences) >= 4:
        score += 5

    return max(0, min(100, score))


@dataclass
class ValidationResult:
    passed: bool
    score: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        parts = [f"{status} ({self.score}/100)"]
        if self.errors:
            parts.append("Errors: " + "; ".join(self.errors[:3]))
        if self.warnings:
            parts.append("Warnings: " + "; ".join(self.warnings[:2]))
        return " | ".join(parts)


def _load_banned_patterns() -> list[tuple[str, re.Pattern[str]]]:
    path = CONFIG_DIR / "banned_phrases.txt"
    patterns: list[tuple[str, re.Pattern[str]]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return patterns
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("regex:"):
            raw = line[6:].strip()
            patterns.append((raw, re.compile(raw, re.I)))
        else:
            escaped = re.escape(line)
            patterns.append((line, re.compile(escaped, re.I)))
    return patterns


def _load_recent_signature_usage(n: int = 5) -> list[str]:
    try:
        archive = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    found: list[str] = []
    for script in archive[:n]:
        spoken = (script.get("spoken_script") or "").lower()
        for phrase in SIGNATURE_PHRASES:
            if phrase in spoken:
                found.append(phrase)
    return found


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?]+\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _first_sentence(text: str) -> str:
    sentences = _sentences(text)
    return sentences[0] if sentences else text.strip()


def _last_sentence(text: str) -> str:
    sentences = _sentences(text)
    return sentences[-1] if sentences else text.strip()


def _normalize_for_match(text: str) -> str:
    return re.sub(r"[^a-z0-9' ]", "", text.lower())


def _phrase_in_script(phrase: str, spoken: str) -> bool:
    if not phrase:
        return True
    return _normalize_for_match(phrase) in _normalize_for_match(spoken)


def _collect_trigger_phrases(script: dict) -> list[tuple[str, str]]:
    """Return (field_label, phrase) pairs that must appear in spoken_script."""
    spoken = script.get("spoken_script") or ""
    triggers = script.get("video_triggers") or {}
    required: list[tuple[str, str]] = []

    beats = triggers.get("beat_phrases") or {}
    crust = beats.get("crust")
    if crust:
        required.append(("beat_phrases.crust", crust))

    for i, phrase in enumerate(triggers.get("fun_phrases") or []):
        if phrase:
            required.append((f"fun_phrases[{i}]", phrase))

    for i, stat in enumerate(triggers.get("stat_phrases") or []):
        if isinstance(stat, dict):
            phrase = stat.get("phrase", "")
            if phrase:
                required.append((f"stat_phrases[{i}]", phrase))

    for i, moment in enumerate(script.get("visual_moments") or []):
        if isinstance(moment, dict):
            phrase = moment.get("at_phrase", "")
            if phrase:
                required.append((f"visual_moments[{i}]", phrase))

    return required


def validate_script(
    script: dict,
    topic: dict | None = None,
    recent_signatures: list[str] | None = None,
) -> ValidationResult:
    """Validate a script against voice, length, trigger, and boundary rules."""
    errors: list[str] = []
    warnings: list[str] = []
    score = 100

    spoken = (script.get("spoken_script") or "").strip()
    if not spoken:
        return ValidationResult(False, 0, ["spoken_script is empty"])

    word_count = len(spoken.split())
    if word_count > MAX_WORDS:
        errors.append(f"Length {word_count} words exceeds max {MAX_WORDS}")
        score -= min(40, (word_count - MAX_WORDS) * 2)

    spoken_lower = spoken.lower()
    for label, pattern in _load_banned_patterns():
        if pattern.search(spoken_lower):
            errors.append(f"Banned phrase matched: {label}")
            score -= 15

    opening = (script.get("opening_line") or "").strip()
    closer = (script.get("loopback_closer") or "").strip()
    first = _first_sentence(spoken)
    last = _last_sentence(spoken)

    if opening and _normalize_for_match(opening) != _normalize_for_match(first):
        errors.append("opening_line does not match first sentence of spoken_script")
        score -= 10

    if closer and _normalize_for_match(closer) != _normalize_for_match(last):
        errors.append("loopback_closer does not match final sentence of spoken_script")
        score -= 10

    for label, phrase in _collect_trigger_phrases(script):
        if not _phrase_in_script(phrase, spoken):
            errors.append(f"Trigger {label} not found verbatim in spoken_script: '{phrase}'")
            score -= 8

    triggers = script.get("video_triggers") or {}
    broll_phrases = triggers.get("broll_phrases") or []
    broll_descs = triggers.get("broll_image_descriptions") or []
    if broll_phrases:
        if len(broll_descs) != len(broll_phrases):
            errors.append(
                f"broll_image_descriptions length ({len(broll_descs)}) must match broll_phrases ({len(broll_phrases)})"
            )
            score -= 12
        for i, phrase in enumerate(broll_phrases):
            if i >= len(broll_descs) or not str(broll_descs[i]).strip():
                errors.append(f"Missing broll_image_descriptions[{i}] for phrase '{phrase}'")
                score -= 8

    sentences = _sentences(spoken)
    if sentences:
        lengths = [len(s.split()) for s in sentences]
        avg_len = sum(lengths) / len(lengths)
        if avg_len > MAX_AVG_SENTENCE_WORDS:
            warnings.append(f"Avg sentence length {avg_len:.1f} words (target ≤{MAX_AVG_SENTENCE_WORDS})")
            score -= 5
        long_sentences = [s for s in sentences if len(s.split()) > MAX_SENTENCE_WORDS]
        if long_sentences:
            warnings.append(f"{len(long_sentences)} sentence(s) exceed {MAX_SENTENCE_WORDS} words")
            score -= 3 * min(len(long_sentences), 3)

    sig_count = sum(1 for p in SIGNATURE_PHRASES if p in spoken_lower)
    if sig_count < MIN_SIGNATURE_PHRASES:
        warnings.append("Missing signature phrase (Right?, That's all it is., etc.)")
        score -= 5
    if sig_count > MAX_SIGNATURE_PHRASES:
        warnings.append(f"Too many signature phrases ({sig_count}, max {MAX_SIGNATURE_PHRASES})")
        score -= 3

    recent = recent_signatures if recent_signatures is not None else _load_recent_signature_usage(5)
    for phrase in SIGNATURE_PHRASES:
        if phrase in spoken_lower and recent.count(phrase) >= 2:
            warnings.append(f"Signature phrase overused recently: '{phrase}'")
            score -= 3

    has_fake_stat = any(re.search(p, spoken_lower) for p in FAKE_STAT_PATTERNS)
    has_experience = any(fr in spoken_lower for fr in EXPERIENCE_FRAMING)
    topic_summary = (topic or {}).get("topic_summary", "").lower()
    if has_fake_stat and not has_experience and not topic_summary:
        warnings.append("Stat cites external source without research context — use experience framing")
        score -= 5

    if topic and topic.get("source_type") != "journal":
        story_score = score_story_quality(script, topic)
        if story_score < STORY_SCORE_THRESHOLD:
            warnings.append(f"Low story score ({story_score}/100) — reads listicle/newsy")
            score -= max(0, (STORY_SCORE_THRESHOLD - story_score) // 3)

    score = max(0, min(100, score))
    passed = len(errors) == 0
    return ValidationResult(passed=passed, score=score, errors=errors, warnings=warnings)

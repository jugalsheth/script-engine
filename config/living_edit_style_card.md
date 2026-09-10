# Living Edit Style Card — Jugal Sheth
### Vibe-Coding Short-Form (Cursor, Claude Code, AI Tools)
*Living document — update after every 10 reels*

---

## Visual Identity — What a Jugal Reel Should Feel Like

Think: **senior engineer explaining something at his desk, not a hype guy selling a course.**

The corpus (29 reels) clocks an average creativity score of 2.62/5 — deliberately understated. That's the brand. Every visual decision should reinforce the same emotional signal: *this person knows what they're doing and doesn't need to prove it with flash.*

- **Lighting:** Natural home/desk light. Soft, directional, no ring-light halo. The 8 "natural home lighting" tags in the corpus aren't accidental — warmth signals authenticity in this niche.
- **Framing:** Chest-up, slightly off-center, face takes ~60% of vertical space. Camera at eye-level or 2° above. Never below chin (YouTube podcast angle kills authority on 9:16).
- **Background:** Desk, monitor visible, IDE open if possible. The dark UI behind you is passive proof you live in this world.
- **Color temperature:** Slightly cool-neutral on face, **dark UI on screen** (6 of 6 screen-heavy reels use dark mode). The contrast between warm face and dark IDE is the palette.
- **Movement:** Almost none. No gimbal drift. No zoom-in pulse on beats. Static camera, performer moves.

---

## Hook Grammar — First 2 Seconds

19 of 29 reels open **face + text simultaneously**. This is the default. No exceptions for walkthrough content.

**The formula:**
1. **Frame 0–0.5s:** Face already mid-sentence or mid-gesture. No lead-in silence. No "hey guys."
2. **Frame 0.5–2s:** Bold hook text appears — top-third or bottom-safe, never mid-frame. Text is **incomplete** — it cuts off or creates an open loop. ("I built a full SaaS in" — cut. "Cursor just did something" — cut.)
3. **Never open on screen record.** Only 1 of 29 reels did this. Screen as opener kills the credibility anchor before it's established.

**Incomplete text rule:** The caption should make no grammatical sense without watching the next 4 seconds. Force the brain to complete the sentence.

---

## Caption & Text-On-Screen Rules

**Primary style:** Bold white box — 90% of corpus reels use it. This is non-negotiable on Jugal's content.

- **Font weight:** Heavy/Black. No light fonts. No italics for primary captions.
- **Placement:** Bottom-safe zone (bottom 15% of frame, above navigation bar). Never center-screen during talking head — it covers the face.
- **Length per caption:** 3–6 words maximum. Not full sentences. Single idea per frame.
- **Stat overlays:** Use sparingly — 4 instances in corpus. When a number matters (lines of code, time saved, tokens used), pop it in high-contrast yellow or white, centered, 1.5× the caption font size. One per video.
- **No subtitle bars** (only 6 uses in corpus, feels like auto-generated content). Avoid bold yellow bars — 2 uses, both feel off-brand for this niche.
- **Screen records:** No captions over UI. Let the screen breathe. Step labels only if the UI doesn't make the action obvious.

---

## Cut Rhythm & Pacing

100% of corpus reels clocked as **slow paced**. This is intentional and load-bearing — it's what separates Jugal from AI hype channels.

- **Average shot hold:** 6–11 seconds on face. Don't cut before the thought lands.
- **Face → Screen transition:** Hard cut, zero transition effects. The abruptness signals confidence. Wipes, fades, and swipes signal amateur.
- **Cut on speech beats:** Cut when the sentence ends or at a natural breath, not on random timecodes.
- **Screen record pacing:** Don't rush the UI. If you're clicking through Cursor, hold on each step for 4–6 seconds. Viewers need to follow.
- **Return to face:** Come back to face for the closer or at a "did you see that?" reaction beat. 13 of 29 reels use face→screen, 5 use face→screen→face. The bookend structure is proven.

---

## B-Roll & Proof Shots

**UI always beats abstract.** The 5 "dark UI broll" tags in the corpus represent the only B-roll worth using.

**Hierarchy of proof shots:**
1. **Screen record of the actual tool** (Cursor, Claude Code, the terminal) — highest trust
2. **Screenshot of the output** (the built component, the generated file, the token count)
3. **Product UI still** with cursor visible — shows you actually ran it
4. **Nothing** — face only is better than stock footage or AI-generated visuals

**Never use:** Abstract AI brain animations, generic code stock footage, floating 3D logos, particle effects. These were flagged in the avoid patterns and signal "I didn't actually build this."

---

## Remotion vs Capture — What to Auto vs What to Film

| Element | Method |
|---|---|
| Captions/subtitles | Remotion — auto-generate from transcript, apply bold white box style |
| Stat overlays (numbers, token counts, time) | Remotion — programmatic, synced to speech beat |
| Step labels on screen record | Remotion — simple text, appears/disappears on cut |
| Hook text (incomplete sentence) | Remotion — timed to frame 0.5s, bold, top-third |
| Face footage | Capture — no exceptions, no AI avatar |
| Screen record | Capture — OBS or native recorder, dark mode always |
| Reaction/proof beat (face returning post-screen) | Capture — film a dedicated "reaction to result" clip |
| Transitions | Neither — hard cuts only, no Remotion animations between clips |

---

## 3 Edit Recipes — Jugal's Defaults

### Recipe 1: FACE_HOOK_SCREEN_PROOF
**Use when:** Sharing a specific Cursor/Claude move someone can copy today.

```
[0–2s]   Face, mid-sentence, bold incomplete hook text top-third
[2–3s]   Hard cut to full-screen screen record
[3–25s]  Screen walkthrough — slow, deliberate, step by step
[25–30s] Hard cut back to face — closer line, stat overlay pops
```

**Capture needs:** 1 talking head clip (hook + closer filmed together), 1 screen record of the exact flow.
**Remotion adds:** Hook text, stat at closer, step label on the one non-obvious UI moment.

---

### Recipe 2: CONFESSION_STAT
**Use when:** Sharing a realization, mistake, or counterintuitive take about vibe-coding workflow.

```
[0–1s]   Face only — no text — emotion first
[1–15s]  Face continuous, slow delivery, one UI screenshot insert at proof beat
[15–20s] Stat or receipt moment — Remotion stat overlay pops
[20–25s] Face closes — no CTA softness, end on the point
```

**Capture needs:** 1 continuous talking head clip, 1 screenshot of the receipt/proof.
**Remotion adds:** Stat overlay at payoff, bottom-safe captions throughout.

---

### Recipe 3: WALKTHROUGH (Series Style)
**Use when:** Installing a tool, showing a multi-step Cursor workflow, "Part X of Y" content.

```
[0–3s]   Face + series label text box top-third ("Part 3 — Cursor Rules")
[3–5s]   Hard cut to full-screen UI
[5–55s]  Continuous screen record, face never returns until closer
[55–60s] Face closes with one-line takeaway
```

**Capture needs:** 5–8s face hook clip, full screen record of complete flow, 5s face closer.
**Remotion adds:** Series label on hook, optional step counters (Step 1 / Step 2) in bottom-safe zone.

---

## Steal List — 5 Techniques Adapted from Corpus

1. **Incomplete hook text** *(from FACE_HOOK_SCREEN_PROOF pattern, 177K likes reference)* — Write the hook caption so it cuts off mid-thought. "I gave Claude the entire codebase and it—" forces a watch. Apply to every Recipe 1 video.

2. **Series counter format** *(from day-counter/part-X pattern)* — "Cursor Workflow 07" in the top-third hook box. Builds episodic habit. Viewers who missed part 6 feel FOMO, not confusion.

3. **Single yellow accent number** *(from color pop technique in corpus)* — When the stat is the point (3 hours saved, 400 lines generated), isolate that number in bright yellow against the white caption. One per video, maximum.

4. **Hard cut face → dark IDE** *(dominant in 13/29 reels)* — No transition. The jump itself is the edit. The darkness of the IDE screen against the warm face creates instant visual contrast without any motion graphics.

5. **Hand gesture as visual punctuation** *(from high-engagement talking head analysis)* — When naming the tool or the key move, the hand comes up. Not performative — one deliberate gesture per key term. Eliminates need for B-roll on confession-style videos.

---

## Hard Avoids

- **No AI-generated visuals as B-roll.** Neural network animations, glowing brain graphics, abstract data streams — all signal "I'm talking about AI, not using it." Your screen record is the proof. Use it.
- **No music-driven edits.** Don't cut to beats. Don't add lo-fi background. Clean audio, voice forward. The 29-reel corpus has zero beat-matched edits.
- **No jump-cut rapid fire.** Every reel in the corpus is slow. Jugal's authority is built on sustained eye contact and deliberate delivery. Jump cuts would make him look like a clip farmer, not an engineer.
- **No over-captioning.** If the caption is a full sentence, it's too long. If there are more than 2 text elements visible simultaneously, it's too cluttered.
- **No generic hooks.** "This AI tool will blow your mind" — avoid. "I replaced my PR review process with one Cursor rule" — use. Specificity is the hook.
- **No transition effects between face and screen.** Zero. Hard cuts only.

---

## Before/After — Boring vs On-Brand

### Pair 1: The Hook

| ❌ Boring | ✅ On-Brand |
|---|---|
| Starts with 2 seconds of silence, creator adjusting mic | Starts mid-sentence, hand already moving |
| Caption: "AI Tools That Will Change Your Life" (full sentence, centered) | Caption: "Claude just rewrote my entire—" (cut off, top-third, bold white box) |
| Fade-in from black | Frame 1 is already face, already talking |

---

### Pair 2: The Screen Transition

| ❌ Boring | ✅ On-Brand |
|---|---|
| Creator says "so let me show you" and then wipes/slides to screen | Creator says "so let me show you" — hard cut, screen is already there |
| Screen record has light mode IDE with small font | Dark mode IDE, font size bum

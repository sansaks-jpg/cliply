"""Highlight detection prompts and constants.

Contains LLM prompt templates for the 3-stage highlight detection pipeline:
  Stage 1: Content type & density
  Stage 2: Narrative segmentation
  Stage 3: Highlight generation
"""

# ── Stage 1: Content Type & Density ───────────────────────────────

CONTENT_TYPE_PROMPT = """Analyze these transcript samples taken from the BEGINNING, MIDDLE, and END of the video
(to catch tonal/density shifts across the video, not just the opening).

Choose content_type: podcast, interview, tutorial, lecture, commentary, debate, vlog, other.
Estimate density: low (mostly filler/chit-chat), medium, high (dense info/stories).
If density clearly shifts between sections, report the density of the densest contiguous
block and set density_shifts to true.

Respond with JSON only:
{"content_type":"...","density":"...","density_shifts":boolean}"""


# ── Stage 2: Narrative Segmentation ───────────────────────────────

NARRATIVE_SEGMENTATION_PROMPT = """
You are mapping the narrative structure of a Mobile Legends streaming transcript.
Do NOT select highlights yet — your only job is identifying coherent narrative units
AND classifying each by its viral content category.

A narrative unit is a contiguous span covering ONE topic, story, argument, or exchange.
Boundaries fall at natural topic shifts — not at arbitrary time intervals.

For each unit, determine:
- start_segment_id, end_segment_id (must exactly match segment IDs below)
- topic: one-line description of what's being discussed
- arc_type: "story" | "argument" | "single_point" | "q_and_a" | "tips_list" | "filler"
- arc_complete: true only if this span has a natural beginning AND resolution/payoff
  entirely within these boundaries
- intensity: 0-100
- clip_category: classify this unit into EXACTLY ONE of:
    "SAVAGE_CLUTCH"       — multi-kill, 1v5, comeback dramatis, clutch moments
    "TIPS_BUILD"          — tutorial hero, build guide, counter tips, META discussion
    "TROLL_FAIL"          — troll build, unorthodox play, epic fail moments
    "RANT_OPINI"          — rant about rank system, broken hero/META, game opinions
    "DRAMA_SOSIAL"        — gossip, streamer drama, ngomongin orang/kejadian di luar game
    "BOCIL_ENCOUNTER"     — toxic teammate, bocil drama, feeder, curhat rank
    "VIEWER_INTERACTION"  — donation reactions, viewer challenges, chat interaction
    "PRO_SCENE"           — MPL/esports analysis, pro player opinion, draft commentary
    "FILLER"              — loading screen, dead air, off-topic small talk with no payoff
- has_payoff: true if there is a clear climactic moment within the unit —
  kill confirmed, punchline landed, reveal made, reaction peaked, argument resolved

Content type: {content_type} | Density: {density}

Rules:
- Unit length is determined by where the topic actually starts/ends — NOT by any target duration
- Max duration per unit: 180 seconds. If a topic runs longer, split into part 1, part 2, etc.
- Merge arc_complete=false short units with adjacent units until the span resolves,
  unless merging would exceed 180s or cross into a different clip_category
- Every segment must belong to exactly one unit — no gaps, no overlaps
- Isolate FILLER as its own units — do not merge FILLER into content-bearing units
- clip_category must reflect the PRIMARY content of the unit, not a secondary moment

Respond ONLY with valid JSON:
{{"units":[{{"start_segment_id":int,"end_segment_id":int,"topic":"string","arc_type":"string","arc_complete":bool,"intensity":int,"clip_category":"string","has_payoff":bool}}]}}

Transcript:
{transcript}"""


# ── Stage 3: Highlight Generation ─────────────────────────────────

HIGHLIGHT_SYSTEM_PROMPT = """You are an elite short-form video editor who has studied thousands of viral clips on TikTok,
Instagram Reels, and YouTube Shorts. You know exactly what makes viewers stop scrolling,
watch to the end, and share.

You have already been given a narrative map of this video. Use it — do not treat the raw
transcript as a flat list of lines to scan for punchy sentences. Every highlight must
correspond to ONE narrative unit, or a contiguous merge of adjacent units, from this map.
Never cut a unit with arc_complete=true short — output its full boundaries.

Narrative map:
{narrative_map}

Virality signals to prioritize (ranked by impact):
1. HOOK MOMENTS — statements that create immediate curiosity
2. EMOTIONAL PEAKS — genuine surprise, laughter, anger, vulnerability, excitement
3. OPINION BOMBS — strong, polarizing or counter-intuitive statements
4. REVELATION MOMENTS — surprising facts, stats, or confessions
5. CONFLICT/TENSION — disagreement, pushback, or a problem confronted head-on
6. QUOTABLE ONE-LINERS — a sentence that works as a standalone quote card
7. STORY PEAKS — the climax or twist of an anecdote
8. PRACTICAL VALUE — a concrete tip, hack, or insight

Content type: {content_type} | Density: {density}

Selection rules:
- Prefer units with arc_complete=true and high intensity
- Duration is a CONSEQUENCE of the unit's real boundaries, not a target. A complete story
  that runs 140 seconds is output as 140 seconds — never trimmed to fit a "sweet spot"
- Only use an arc_complete=false unit if you can independently verify the exact sub-span
  you're quoting is self-contained — this is an exception, not the default
- Hard limits: minimum 15s, maximum 180s. If a complete arc exceeds 180s, find the tightest
  internally-complete sub-arc and explain the tradeoff in "reasoning"
- start_segment_id / end_segment_id must exactly match segment IDs in the transcript — never invent them
- Two highlights may not share more than 20% of their segment range
- Generate at least 5 highlights, ranked by score descending

For each highlight:
- "reasoning": 2-3 sentences — what's the complete arc here, why these exact boundaries,
  what breaks if you cut earlier or later
- "hook_sentence": exact opening line (quoted verbatim from transcript) that earns the first 3 seconds
- "virality_reason": one sentence
- "score": 0-100 viral potential (not general quality)

Respond ONLY with valid JSON (no markdown):
{{"highlights":[{{"title":"string","start_segment_id":int,"end_segment_id":int,"reasoning":"string","score":int,"hook_sentence":"string","virality_reason":"string"}}]}}

Transcript:
{transcript}"""


# ── Stage 3: Gaming Highlight Generation ────────────────────────────

HIGHLIGHT_SYSTEM_PROMPT_GAMING = """
You are an elite clipper for Mobile Legends Indonesia streaming content. You have studied
thousands of viral ML clips on TikTok, Instagram Reels, and YouTube Shorts. You know exactly
what makes Indonesian ML viewers stop scrolling, watch to the end, and share.

You have already been given a narrative map with each unit pre-labeled by clip_category and has_payoff.
Use this map — do not treat the raw transcript as a flat list of lines to scan.
Every highlight must correspond to ONE narrative unit, or a contiguous merge of adjacent
units with the SAME clip_category, from this map.
Never cut a unit with arc_complete=true short — output its full boundaries.

Narrative map:
{narrative_map}

## Category-Specific Virality Logic

Each clip_category has different virality triggers. Score accordingly:

SAVAGE_CLUTCH
  Viral when: peak vocalization coincides with kill confirmation, commentary energy spikes,
  real-time reaction is audible. Prefer units where the streamer screams DURING the kill,
  not just after.
  Hook target: the moment of tension BEFORE the kill lands.

TIPS_BUILD
  Viral when: the insight is surprising or counterintuitive, delivered with specific numbers
  or hero names, and the opener implies a revelation ("Kalau lo build ini...", "Kebanyakan
  orang salah di sini..."). Must feel immediately applicable.
  Hook target: confident opening claim that promises a payoff for watching.

TROLL_FAIL
  Viral when: the absurdity clearly escalates, then has a visible punchline or unexpected
  outcome. The setup must signal "something dumb is about to happen."
  Hook target: the moment the stupid decision is made or announced.

RANT_OPINI
  Viral when: the frustration is specific (not vague), articulated aggressively enough
  that viewers feel "ini gue banget" OR disagree strongly enough to comment and argue.
  Vague complaints do not go viral. Specific targets (a hero, a mechanic, a rank bracket)
  with a clear grievance do.
  Hook target: the bold opening claim or accusation, before any hedging.

DRAMA_SOSIAL
  Viral when: a specific name or incident is referenced with emotional energy. Stakes must
  feel personal or scandalous. Ambiguous references ("ada orang sih...") have low virality;
  direct references have high virality.
  Hook target: name-drop or scandal tease in the first line.

BOCIL_ENCOUNTER
  Viral when: streamer's reaction to absurd teammate behavior is authentic and escalating.
  Highest virality when there is a punchline moment (streamer gives up, says something absurd,
  or the outcome is ironically catastrophic).
  Hook target: the moment the toxic/bocil behavior is first acknowledged and named.

VIEWER_INTERACTION
  Viral when: streamer reaction is genuine and extreme — shock, uncontrollable laughter,
  visible emotion. The buildup-to-reaction arc must be complete within the clip.
  Hook target: the moment the interaction lands and the streamer reacts.

PRO_SCENE
  Viral when: the opinion is bold, specific, and attributable to a real player, team,
  or match. Hedged takes ("mungkin sih...") have low virality. Confident takes with
  reasoning earn comment-section debate which drives reach.
  Hook target: the bold statement before qualifications.

Content type: {content_type} | Density: {density}

## Selection Rules
- Skip any unit with clip_category="FILLER" — they are never highlights
- Prefer units with arc_complete=true AND has_payoff=true
- Units with arc_complete=true but has_payoff=false are acceptable if intensity >= 70
- Duration is a CONSEQUENCE of the unit's real boundaries, not a target
- Hard limits: minimum 15s, maximum 180s. If a complete arc exceeds 180s, find the
  tightest internally-complete sub-arc and explain the tradeoff in "reasoning"
- start_segment_id / end_segment_id must exactly match segment IDs in the transcript
- Two highlights may not share more than 20% of their segment range
- Generate at least 5 highlights, ranked by score descending
- Represent at least 2 different clip_categories if the content supports it —
  a one-dimensional clip selection is a red flag

## Output Fields Per Highlight
- "clip_category": one of the 8 categories (not FILLER)
- "title": descriptive, max 8 words
- "start_segment_id" / "end_segment_id": exact match from transcript
- "reasoning": 2-3 sentences — what is the complete arc, why these boundaries,
  what breaks if cut earlier or later
- "hook_sentence": exact verbatim opening line from transcript that earns the first 3 seconds
- "hook_type": one phrase describing WHY this hook works for its category
  (e.g., "tension before kill", "bold counterintuitive claim", "name-drop tease")
- "virality_reason": one sentence tied to the specific category's virality logic
- "score": 0-100 viral potential. Measure: how likely is an average Indonesian ML
  TikTok viewer (17-25yo) to stop scrolling, watch to the end, and comment or share?

Respond ONLY with valid JSON (no markdown):
{{"highlights":[{{"title":"string","clip_category":"string","start_segment_id":int,"end_segment_id":int,"reasoning":"string","score":int,"hook_sentence":"string","hook_type":"string","virality_reason":"string"}}]}}

Transcript:
{transcript}"""


# ── Constants ─────────────────────────────────────────────────────

CHUNK_SIZE_SECONDS = 1200
LONG_VIDEO_THRESHOLD = 1800
CHUNK_OVERLAP_SECONDS = 60
MAX_HIGHLIGHT_ATTEMPTS = 2
MAX_OVERLAP_RATIO = 0.20
MIN_DURATION = 15
MAX_DURATION = 180

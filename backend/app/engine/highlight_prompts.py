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

NARRATIVE_SEGMENTATION_PROMPT = """You are mapping the narrative structure of a video transcript. Do NOT select highlights yet —
your only job is identifying coherent narrative units.

A narrative unit is a contiguous span covering ONE topic, story, argument, or exchange.
Boundaries fall at natural topic shifts (new subject, new question, "anyway", "so basically",
a punchline landing) — not at arbitrary time intervals.

For each unit, determine:
- start_segment_id, end_segment_id (must exactly match segment IDs below)
- topic: one-line description of what's being discussed
- arc_type: "story" | "argument" | "single_point" | "q_and_a" | "tips_list" | "filler"
- arc_complete: true only if this span has a natural beginning AND resolution/payoff
  entirely within these boundaries. false if understanding it requires context outside the span.
- intensity: 0-100, how emotionally or informationally charged

Content type: {content_type} | Density: {density}

Rules:
- Unit length is determined by where the topic actually starts/ends — NOT by any target duration.
- Max duration of a narrative unit should not exceed 180 seconds. If a topic is longer than 180 seconds, split it into multiple units (e.g., topic part 1, part 2).
- If a unit has arc_complete=false and is short, merge it with adjacent units until the merged span
  resolves (arc_complete=true), unless the thread genuinely never resolves in this video or it would exceed 180 seconds.
- Every segment must belong to exactly one unit — cover the full transcript without gaps or overlaps.

Respond ONLY with valid JSON:
{{"units":[{{"start_segment_id":int,"end_segment_id":int,"topic":"string","arc_type":"string","arc_complete":bool,"intensity":int}}]}}

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


# ── Constants ─────────────────────────────────────────────────────

CHUNK_SIZE_SECONDS = 1200
LONG_VIDEO_THRESHOLD = 1800
CHUNK_OVERLAP_SECONDS = 60
MAX_HIGHLIGHT_ATTEMPTS = 3
MAX_OVERLAP_RATIO = 0.20
MIN_DURATION = 15
MAX_DURATION = 180

"""Find viral-worthy highlights in a transcript.

3-stage architecture:
  Stage 1: Content type & density (samples beginning/middle/end)
  Stage 2: Narrative segmentation (maps story structure)
  Stage 3: Highlight generation (uses narrative map, segment IDs)

Key improvement: model works from a narrative map, not raw transcript.
Segment IDs prevent timestamp hallucination.
"""
import json
import re
from typing import Dict, List, Optional

from .llm import LLMFn, get_llm_fn

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
- Unit length is determined by where the topic actually starts/ends — NOT by any target duration
- If a unit has arc_complete=false, merge it with adjacent units until the merged span
  resolves (arc_complete=true), unless the thread genuinely never resolves in this video
- Every segment must belong to exactly one unit — cover the full transcript

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
- "hook_sentence": exact opening line (quoted from transcript) that earns the first 3 seconds
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


# ── Helpers ───────────────────────────────────────────────────────

def _parse_json_loose(raw: str) -> Dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])
        raise


def _coerce_float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _coerce_int(v, default=0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


# ── Transcript Formatting ─────────────────────────────────────────

def build_transcript_text(transcript: Dict) -> str:
    """Format transcript with segment IDs: [id][timestamp] [speaker]: text"""
    lines = []
    for i, s in enumerate(transcript.get("segments", [])):
        speaker = s.get("speaker")
        speaker_str = f" [{speaker}]:" if speaker else ""
        lines.append(f"[{i}][{s['start']:.1f}s]{speaker_str} {s['text'].strip()}")
    return "\n".join(lines)


def build_transcript_samples(transcript: Dict) -> str:
    """Sample beginning, middle, end for content type detection."""
    segments = transcript.get("segments", [])
    n = len(segments)
    if n == 0:
        return ""
    
    # Beginning: first 10 segments
    begin = segments[:10]
    # Middle: 10 segments around the midpoint
    mid_idx = n // 2
    middle = segments[max(0, mid_idx - 5):mid_idx + 5]
    # End: last 10 segments
    end = segments[-10:]
    
    def fmt(segs, offset=0):
        return "\n".join(
            f"[{offset + i}][{s['start']:.1f}s] {s['text'].strip()}"
            for i, s in enumerate(segs)
        )
    
    return f"""--- BEGINNING ---
{fmt(begin, 0)}

--- MIDDLE ---
{fmt(middle, mid_idx - 5)}

--- END ---
{fmt(end, n - 10)}"""


def _segment_map(transcript: Dict) -> Dict[int, Dict]:
    """Build segment ID → {start, end, text} mapping."""
    segments = transcript.get("segments", [])
    return {
        i: {"start": s["start"], "end": s["end"], "text": s["text"]}
        for i, s in enumerate(segments)
    }


# ── Stage 1: Content Type & Density ──────────────────────────────

def detect_content_type(transcript: Dict, llm_fn: LLMFn) -> Dict[str, str]:
    samples = build_transcript_samples(transcript)
    prompt = f"{CONTENT_TYPE_PROMPT}\n\n{samples}"
    try:
        raw = llm_fn(prompt)
        return _parse_json_loose(raw)
    except Exception:
        return {"content_type": "other", "density": "medium", "density_shifts": False}


# ── Stage 2: Narrative Segmentation ──────────────────────────────

def segment_narrative(transcript: Dict, content_info: Dict, llm_fn: LLMFn) -> List[Dict]:
    """Map narrative structure. Returns list of units with segment IDs."""
    transcript_text = build_transcript_text(transcript)
    prompt = NARRATIVE_SEGMENTATION_PROMPT.format(
        content_type=content_info.get("content_type", "other"),
        density=content_info.get("density", "medium"),
        transcript=transcript_text,
    )
    
    last_error = "unknown"
    for attempt in range(1, MAX_HIGHLIGHT_ATTEMPTS + 1):
        raw = llm_fn(prompt)
        try:
            parsed = _parse_json_loose(raw)
            units = parsed.get("units", [])
            if units:
                validated = _validate_units(units, transcript)
                if validated:
                    return validated
                last_error = "no valid units after validation"
            else:
                last_error = "empty units array"
        except Exception as e:
            last_error = str(e)
        
        if attempt < MAX_HIGHLIGHT_ATTEMPTS:
            prompt = f"{prompt}\n\nIMPORTANT: Return ONLY valid JSON with a top-level 'units' array. Each item must include: start_segment_id (int), end_segment_id (int), topic (string), arc_type (string), arc_complete (bool), intensity (0-100). No markdown fences."
    
    raise RuntimeError(f"Narrative segmentation failed after {MAX_HIGHLIGHT_ATTEMPTS} attempts: {last_error}")


def _validate_units(units: List[Dict], transcript: Dict) -> List[Dict]:
    """Validate narrative units: segment IDs exist, ranges make sense, full coverage."""
    segments = transcript.get("segments", [])
    n_segments = len(segments)
    if n_segments == 0:
        return []
    
    valid_types = {"story", "argument", "single_point", "q_and_a", "tips_list", "filler"}
    validated = []
    
    for u in units:
        start_id = _coerce_int(u.get("start_segment_id"), -1)
        end_id = _coerce_int(u.get("end_segment_id"), -1)
        
        if start_id < 0 or end_id < start_id or end_id >= n_segments:
            continue
        
        arc_type = str(u.get("arc_type", "single_point")).strip().lower()
        if arc_type not in valid_types:
            arc_type = "single_point"
        
        validated.append({
            "start_segment_id": start_id,
            "end_segment_id": end_id,
            "start_time": segments[start_id]["start"],
            "end_time": segments[end_id]["end"],
            "topic": str(u.get("topic", "")).strip(),
            "arc_type": arc_type,
            "arc_complete": bool(u.get("arc_complete", False)),
            "intensity": max(0, min(100, _coerce_int(u.get("intensity"), 50))),
        })
    
    return validated


# ── Stage 3: Highlight Generation ────────────────────────────────

def generate_highlights(
    transcript: Dict,
    narrative_units: List[Dict],
    content_info: Dict,
    num_clips: int,
    llm_fn: LLMFn,
) -> List[Dict]:
    """Generate highlights using narrative map. Returns validated highlights with segment IDs."""
    transcript_text = build_transcript_text(transcript)
    narrative_json = json.dumps({"units": narrative_units}, indent=2)
    
    prompt = HIGHLIGHT_SYSTEM_PROMPT.format(
        narrative_map=narrative_json,
        content_type=content_info.get("content_type", "other"),
        density=content_info.get("density", "medium"),
        transcript=transcript_text,
    )
    
    last_error = "unknown"
    for attempt in range(1, MAX_HIGHLIGHT_ATTEMPTS + 1):
        raw = llm_fn(prompt)
        try:
            parsed = _parse_json_loose(raw)
            highlights = parsed.get("highlights", [])
            if highlights:
                validated = _validate_highlights(highlights, transcript, num_clips)
                if validated:
                    return validated
                last_error = "no valid highlights after validation"
            else:
                last_error = "empty highlights array"
        except Exception as e:
            last_error = str(e)
        
        if attempt < MAX_HIGHLIGHT_ATTEMPTS:
            prompt = f"{prompt}\n\nIMPORTANT: Return ONLY valid JSON with a top-level 'highlights' array. Each item must include: title, start_segment_id (int), end_segment_id (int), reasoning (2-3 sentences), score (0-100), hook_sentence (exact quote from transcript), virality_reason. No markdown fences."
    
    raise RuntimeError(f"Highlight generation failed after {MAX_HIGHLIGHT_ATTEMPTS} attempts: {last_error}")


def _validate_highlights(highlights: List[Dict], transcript: Dict, num_clips: int) -> List[Dict]:
    """Validate highlights: segment IDs, duration, overlap."""
    segments = transcript.get("segments", [])
    n_segments = len(segments)
    if n_segments == 0:
        return []
    
    validated = []
    for h in highlights:
        start_id = _coerce_int(h.get("start_segment_id"), -1)
        end_id = _coerce_int(h.get("end_segment_id"), -1)
        
        if start_id < 0 or end_id < start_id or end_id >= n_segments:
            continue
        
        start_time = segments[start_id]["start"]
        end_time = segments[end_id]["end"]
        duration = end_time - start_time
        
        if duration < MIN_DURATION or duration > MAX_DURATION:
            continue
        
        # Check overlap with existing highlights
        overlap_ok = True
        for existing in validated:
            overlap_start = max(start_id, existing["start_segment_id"])
            overlap_end = min(end_id, existing["end_segment_id"])
            overlap_range = max(0, overlap_end - overlap_start + 1)
            this_range = end_id - start_id + 1
            if this_range > 0 and overlap_range / this_range > MAX_OVERLAP_RATIO:
                overlap_ok = False
                break
        
        if not overlap_ok:
            continue
        
        # Extract hook sentence from transcript
        hook = str(h.get("hook_sentence", "")).strip()
        if not hook:
            hook = segments[start_id]["text"].strip()
        
        validated.append({
            "title": str(h.get("title", "Untitled")).strip(),
            "start_segment_id": start_id,
            "end_segment_id": end_id,
            "start_time": start_time,
            "end_time": end_time,
            "score": max(0, min(100, _coerce_int(h.get("score"), 0))),
            "reasoning": str(h.get("reasoning", "")).strip(),
            "hook_sentence": hook,
            "virality_reason": str(h.get("virality_reason", "")).strip(),
        })
    
    # Sort by score, return top N
    validated.sort(key=lambda x: x["score"], reverse=True)
    return validated[:num_clips * 2]  # return extra for dedupe upstream


# ── Main Entry Point ─────────────────────────────────────────────

def get_highlights(
    transcript: Dict,
    num_clips: int = 3,
    llm_fn: LLMFn | None = None,
) -> Dict:
    llm_fn = llm_fn or get_llm_fn()
    duration = transcript.get("duration", 0)
    segments = transcript.get("segments", [])
    seg_map = _segment_map(transcript)
    
    # Stage 1: Content type & density
    content_info = detect_content_type(transcript, llm_fn=llm_fn)
    
    # Stage 2: Narrative segmentation
    narrative_units = segment_narrative(transcript, content_info, llm_fn=llm_fn)
    
    # Stage 3: Highlight generation
    if duration >= LONG_VIDEO_THRESHOLD:
        # For long videos, chunk the narrative units and process per chunk
        highlights = _generate_chunked(transcript, narrative_units, content_info, num_clips, llm_fn)
    else:
        highlights = generate_highlights(transcript, narrative_units, content_info, num_clips, llm_fn)
    
    return {"highlights": highlights, "narrative_units": narrative_units}


def _generate_chunked(
    transcript: Dict,
    narrative_units: List[Dict],
    content_info: Dict,
    num_clips: int,
    llm_fn: LLMFn,
) -> List[Dict]:
    """Process long videos by chunking narrative units."""
    segments = transcript.get("segments", [])
    duration = transcript.get("duration", 0)
    
    all_highlights = []
    start = 0
    while start < duration:
        end = min(start + CHUNK_SIZE_SECONDS, duration)
        
        # Get units in this chunk
        chunk_units = [
            u for u in narrative_units
            if u["start_time"] >= start and u["end_time"] <= end + CHUNK_OVERLAP_SECONDS
        ]
        
        if chunk_units:
            # Get segments in this chunk
            chunk_segments = [
                s for s in segments
                if s["start"] >= start and s["end"] <= end + CHUNK_OVERLAP_SECONDS
            ]
            if chunk_segments:
                chunk_transcript = {"duration": end - start, "segments": chunk_segments}
                chunk_highlights = generate_highlights(chunk_transcript, chunk_units, content_info, num_clips, llm_fn)
                
                # Adjust timestamps back to original
                for h in chunk_highlights:
                    h["start_time"] += start
                    h["end_time"] += start
                    all_highlights.append(h)
        
        start += CHUNK_SIZE_SECONDS - CHUNK_OVERLAP_SECONDS
    
    return all_highlights


def chunk_transcript(transcript: Dict) -> List[Dict]:
    """Legacy function for compatibility."""
    return [transcript]

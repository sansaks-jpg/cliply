"""Find viral-worthy highlights in a transcript.

3-stage architecture:
  Stage 1: Content type & density (samples beginning/middle/end)
  Stage 2: Narrative segmentation (maps story structure)
  Stage 3: Highlight generation (uses narrative map, segment IDs)

Key improvement: model works from a narrative map, not raw transcript.
Segment IDs prevent timestamp hallucination.
"""
import json
import logging
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional

from .llm import LLMFn, get_llm_fn
from ..config import HIGHLIGHT_MAX_WORKERS, LLM_PROVIDER

logger = logging.getLogger(__name__)

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
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError, KeyError):
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
    
    last_errors = []
    current_prompt = prompt
    for attempt in range(1, MAX_HIGHLIGHT_ATTEMPTS + 1):
        raw = llm_fn(current_prompt)
        try:
            parsed = _parse_json_loose(raw)
            units = parsed.get("units", [])
            if units:
                validated = _validate_units(units, transcript)
                if validated:
                    return validated
                err_msg = "no valid units after validation (possibly segment mapping failed)"
            else:
                err_msg = "empty units array or incorrect JSON format"
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError, KeyError) as e:
            err_msg = f"JSON parse error: {e}"
        
        last_errors.append(f"Attempt {attempt} failed: {err_msg}")
        logger.warning(f"[SEGMENTATION] Attempt {attempt} failed: {err_msg}")
        
        if attempt < MAX_HIGHLIGHT_ATTEMPTS:
            feedback_str = "\n".join(last_errors)
            current_prompt = (
                f"{prompt}\n\n"
                f"[PREVIOUS ATTEMPTS FEEDBACK]\n"
                f"Your previous output(s) failed validation with the following errors:\n"
                f"{feedback_str}\n\n"
                f"Please correct these mistakes. Return ONLY valid JSON with a top-level 'units' array conforming to the specifications. Ensure all segment IDs are correct and cover the full transcript."
            )
    
    raise RuntimeError(f"Narrative segmentation failed after {MAX_HIGHLIGHT_ATTEMPTS} attempts: {last_errors[-1]}")


def _validate_units(units: List[Dict], transcript: Dict) -> List[Dict]:
    """Validate narrative units: segment IDs exist, ranges make sense, full coverage."""
    segments = transcript.get("segments", [])
    n_segments = len(segments)
    if n_segments == 0:
        logger.warning("[UNITS] No segments in transcript")
        return []
    
    logger.info(f"[UNITS] Validating {len(units)} raw units against {n_segments} segments")
    valid_types = {"story", "argument", "single_point", "q_and_a", "tips_list", "filler"}
    validated = []
    
    for idx, u in enumerate(units):
        start_id = _coerce_int(u.get("start_segment_id"), -1)
        end_id = _coerce_int(u.get("end_segment_id"), -1)
        
        if start_id < 0 or end_id < start_id or end_id >= n_segments:
            logger.warning(f"[UNITS] #{idx} REJECTED: bad segment IDs start={start_id} end={end_id} (n_segments={n_segments})")
            continue
        
        arc_type = str(u.get("arc_type", "single_point")).strip().lower()
        if arc_type not in valid_types:
            arc_type = "single_point"
            
        intensity = max(0, min(100, _coerce_int(u.get("intensity"), 50)))
        
        # ── Forced Split jika unit melebihi MAX_DURATION ────────────────────────
        # Cap durasi unit agar tidak membuat unit raksasa
        unit_segments = list(range(start_id, end_id + 1))
        current_sub_start = start_id
        
        for seg_idx in unit_segments:
            seg_start = segments[current_sub_start]["start"]
            seg_end = segments[seg_idx]["end"]
            
            # Jika seg_idx adalah segmen terakhir dalam unit, atau jika menambahkan segmen berikutnya melampaui MAX_DURATION
            is_last = (seg_idx == end_id)
            if not is_last:
                next_seg_end = segments[seg_idx + 1]["end"]
                if next_seg_end - seg_start > MAX_DURATION:
                    # Potong di seg_idx saat ini
                    validated.append({
                        "start_segment_id": current_sub_start,
                        "end_segment_id": seg_idx,
                        "start_time": seg_start,
                        "end_time": seg_end,
                        "topic": f"{u.get('topic', '')} (Part {len(validated)+1})",
                        "arc_type": arc_type,
                        "arc_complete": False, # Dipaksa split
                        "intensity": intensity,
                    })
                    current_sub_start = seg_idx + 1
            else:
                # Masukkan sisa unit
                validated.append({
                    "start_segment_id": current_sub_start,
                    "end_segment_id": seg_idx,
                    "start_time": seg_start,
                    "end_time": seg_end,
                    "topic": u.get("topic", "") if current_sub_start == start_id else f"{u.get('topic', '')} (Part {len(validated)+1})",
                    "arc_type": arc_type,
                    "arc_complete": bool(u.get("arc_complete", False)) if current_sub_start == start_id else False,
                    "intensity": intensity,
                })

    if not validated:
        # Fallback jika tidak ada unit valid: buat satu unit raksasa yang mencakup seluruh segmen
        validated.append({
            "start_segment_id": 0,
            "end_segment_id": n_segments - 1,
            "start_time": segments[0]["start"],
            "end_time": segments[-1]["end"],
            "topic": "Full Transcript (Auto-fallback)",
            "arc_type": "filler",
            "arc_complete": False,
            "intensity": 50,
        })
        return validated

    # ── Gap & Overlap Resolution ───────────────────────────────────────────
    # 1. Urutkan berdasarkan start_segment_id
    validated.sort(key=lambda x: x["start_segment_id"])
    
    # 2. Tangani gap di awal (jika unit pertama tidak mulai dari 0)
    if validated[0]["start_segment_id"] > 0:
        validated[0]["start_segment_id"] = 0
        validated[0]["start_time"] = segments[0]["start"]

    # 3. Tangani overlap dan gap antar unit berurutan
    cleaned = []
    for i in range(len(validated) - 1):
        curr_unit = validated[i]
        next_unit = validated[i+1]
        
        curr_end = curr_unit["end_segment_id"]
        next_start = next_unit["start_segment_id"]
        
        if curr_end >= next_start:
            # Overlap! Potong unit saat ini agar berakhir tepat sebelum unit berikutnya dimulai
            new_end = max(curr_unit["start_segment_id"], next_start - 1)
            curr_unit["end_segment_id"] = new_end
            curr_unit["end_time"] = segments[new_end]["end"]
        elif curr_end < next_start - 1:
            # Gap! Perluas unit saat ini agar mengisi gap sampai sebelum unit berikutnya
            new_end = next_start - 1
            curr_unit["end_segment_id"] = new_end
            curr_unit["end_time"] = segments[new_end]["end"]
            
        cleaned.append(curr_unit)
    cleaned.append(validated[-1])
    
    # 4. Tangani gap di akhir (jika unit terakhir tidak sampai n_segments - 1)
    if cleaned[-1]["end_segment_id"] < n_segments - 1:
        cleaned[-1]["end_segment_id"] = n_segments - 1
        cleaned[-1]["end_time"] = segments[-1]["end"]

    logger.info(f"[UNITS] Validation done: {len(cleaned)} units clean and contiguous")
    return cleaned


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
    
    last_errors = []
    current_prompt = prompt
    for attempt in range(1, MAX_HIGHLIGHT_ATTEMPTS + 1):
        raw = llm_fn(current_prompt)
        logger.info(f"[HIGHLIGHTS] Attempt {attempt}: LLM returned {len(raw)} chars")
        try:
            parsed = _parse_json_loose(raw)
            highlights = parsed.get("highlights", [])
            logger.info(f"[HIGHLIGHTS] Attempt {attempt}: parsed {len(highlights)} raw highlights")
            if highlights:
                validated = _validate_highlights(highlights, transcript, num_clips, narrative_units)
                if validated:
                    return validated
                err_msg = "no valid highlights after validation (possibly failed narrative unit bounds constraint)"
            else:
                err_msg = "empty highlights array or incorrect JSON format"
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError, KeyError) as e:
            err_msg = f"JSON parse/validation error: {e}"
            logger.warning(f"[HIGHLIGHTS] Attempt {attempt}: error: {e}")
        
        last_errors.append(f"Attempt {attempt} failed: {err_msg}")
        
        if attempt < MAX_HIGHLIGHT_ATTEMPTS:
            feedback_str = "\n".join(last_errors)
            current_prompt = (
                f"{prompt}\n\n"
                f"[PREVIOUS ATTEMPTS FEEDBACK]\n"
                f"Your previous output(s) failed validation with the following errors:\n"
                f"{feedback_str}\n\n"
                f"Please correct these mistakes. Ensure all highlights align with the provided narrative units (either fully within a single unit, or exact merges of contiguous units), hook sentences match the transcript verbatim, and overlap doesn't exceed 20% cumulative. Respond ONLY with valid JSON."
            )
    
    raise RuntimeError(f"Highlight generation failed after {MAX_HIGHLIGHT_ATTEMPTS} attempts: {last_errors[-1]}")


# ── Alignment Helpers ─────────────────────────────────────────────────

def _align_highlight_to_units(start_id: int, end_id: int, units: List[Dict]) -> tuple[int, int]:
    """Snap start_id and end_id to align with narrative unit boundaries if they are close (within 3 segments)."""
    if not units:
        return start_id, end_id
        
    intersecting_units = [
        u for u in units
        if u["start_segment_id"] <= end_id and start_id <= u["end_segment_id"]
    ]
    if not intersecting_units:
        return start_id, end_id
        
    intersecting_units.sort(key=lambda x: x["start_segment_id"])
    
    # Kasus 1: Berada dalam satu unit narrative
    if len(intersecting_units) == 1:
        u = intersecting_units[0]
        if u["arc_complete"]:
            # Snap ke batas unit penuh jika selisihnya tipis
            if abs(start_id - u["start_segment_id"]) <= 3 and abs(end_id - u["end_segment_id"]) <= 3:
                return u["start_segment_id"], u["end_segment_id"]
        return start_id, end_id
        
    # Kasus 2: Lintas beberapa unit
    first_u = intersecting_units[0]
    last_u = intersecting_units[-1]
    
    new_start = start_id
    new_end = end_id
    
    # Snap ke batas luar unit pertama
    if abs(start_id - first_u["start_segment_id"]) <= 3:
        new_start = first_u["start_segment_id"]
        
    # Snap ke batas luar unit terakhir
    if abs(end_id - last_u["end_segment_id"]) <= 3:
        new_end = last_u["end_segment_id"]
        
    return new_start, new_end


def _is_aligned_with_units(start_id: int, end_id: int, units: List[Dict]) -> bool:
    """Verify if the segment range is strictly aligned with narrative unit boundaries."""
    if not units:
        return True
        
    intersecting_units = [
        u for u in units
        if u["start_segment_id"] <= end_id and start_id <= u["end_segment_id"]
    ]
    if not intersecting_units:
        return False
        
    intersecting_units.sort(key=lambda x: x["start_segment_id"])
    
    # Kasus 1: Berada dalam satu unit narrative
    if len(intersecting_units) == 1:
        u = intersecting_units[0]
        # Jika unit tersebut lengkap (arc_complete=true), highlight tidak boleh memotongnya setengah jalan
        if u["arc_complete"]:
            return start_id == u["start_segment_id"] and end_id == u["end_segment_id"]
        return True
        
    # Kasus 2: Gabungan beberapa unit. Harus mencakup unit-unit tersebut secara utuh dari ujung ke ujung.
    first_u = intersecting_units[0]
    last_u = intersecting_units[-1]
    
    if start_id != first_u["start_segment_id"] or end_id != last_u["end_segment_id"]:
        return False
        
    # Pastikan unit-unitnya berurutan secara rapat (contiguous)
    for idx in range(len(intersecting_units) - 1):
        if intersecting_units[idx]["end_segment_id"] + 1 != intersecting_units[idx+1]["start_segment_id"]:
            return False
            
    return True


# ── Hook Sentence Verification ────────────────────────────────────────

def _normalize_text(text: str) -> str:
    """Normalize text for comparison by removing punctuation and converting to lowercase."""
    return re.sub(r"[^\w\s]", "", text).lower().strip()


def _validate_and_fix_hook(hook: str, start_seg_text: str) -> str:
    """Ensure hook sentence exists in the starting segment, fallback to verbatim text if mismatch."""
    norm_hook = _normalize_text(hook)
    norm_seg = _normalize_text(start_seg_text)
    
    if not norm_hook:
        return start_seg_text.strip()
        
    # Cocokan langsung
    if norm_hook in norm_seg or norm_seg in norm_hook:
        return hook
        
    # Fuzzy match: 50% kata-kata unik cocok
    hook_words = set(norm_hook.split())
    seg_words = set(norm_seg.split())
    if hook_words and len(hook_words & seg_words) / len(hook_words) >= 0.5:
        return hook
        
    # Fallback jika gagal
    return start_seg_text.strip()


# ── Highlight Validation ──────────────────────────────────────────────

def _validate_highlights(
    highlights: List[Dict],
    transcript: Dict,
    num_clips: int,
    narrative_units: Optional[List[Dict]] = None,
) -> List[Dict]:
    """Validate highlights: segment IDs, duration, alignment to narrative units, cumulative overlap."""
    segments = transcript.get("segments", [])
    n_segments = len(segments)
    if n_segments == 0:
        logger.warning("[HIGHLIGHTS] No segments in transcript, returning empty")
        return []
    
    logger.info(f"[HIGHLIGHTS] Validating {len(highlights)} raw highlights against {n_segments} segments")
    
    validated = []
    for idx, h in enumerate(highlights):
        start_id = _coerce_int(h.get("start_segment_id"), -1)
        end_id = _coerce_int(h.get("end_segment_id"), -1)
        
        if start_id < 0 or end_id < start_id or end_id >= n_segments:
            logger.warning(f"[HIGHLIGHTS] #{idx} REJECTED: bad segment IDs start={start_id} end={end_id} (n_segments={n_segments})")
            continue
        
        # 1. Snap/Align boundaries ke unit narrative jika dekat
        if narrative_units:
            start_id, end_id = _align_highlight_to_units(start_id, end_id, narrative_units)
            
            # Verifikasi kecocokan batas unit
            if not _is_aligned_with_units(start_id, end_id, narrative_units):
                logger.warning(f"[HIGHLIGHTS] #{idx} REJECTED: range {start_id}-{end_id} violates narrative unit boundaries")
                continue
        
        start_time = segments[start_id]["start"]
        end_time = segments[end_id]["end"]
        duration = end_time - start_time
        
        if duration < MIN_DURATION:
            logger.warning(f"[HIGHLIGHTS] #{idx} REJECTED: too short {duration:.1f}s < {MIN_DURATION}s (seg {start_id}-{end_id})")
            continue
        if duration > MAX_DURATION:
            logger.warning(f"[HIGHLIGHTS] #{idx} REJECTED: too long {duration:.1f}s > {MAX_DURATION}s (seg {start_id}-{end_id})")
            continue
        
        # 2. Check cumulative overlap (tidak boleh lebih dari 20% kumulatif dari segmen yang sudah diambil)
        total_segments = end_id - start_id + 1
        overlap_count = 0
        for seg_id in range(start_id, end_id + 1):
            for existing in validated:
                if existing["start_segment_id"] <= seg_id <= existing["end_segment_id"]:
                    overlap_count += 1
                    break
        
        overlap_ratio = overlap_count / total_segments if total_segments > 0 else 0
        if overlap_ratio > MAX_OVERLAP_RATIO:
            logger.warning(f"[HIGHLIGHTS] #{idx} REJECTED: cumulative overlap {overlap_ratio*100:.1f}% > {MAX_OVERLAP_RATIO*100:.0f}%")
            continue
        
        # 3. Verifikasi dan perbaiki hook sentence agar verbatim
        hook = str(h.get("hook_sentence", "")).strip()
        hook = _validate_and_fix_hook(hook, segments[start_id]["text"])
        
        logger.info(f"[HIGHLIGHTS] #{idx} ACCEPTED: {duration:.1f}s seg {start_id}-{end_id} score={h.get('score')}")
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
    
    # Urutkan berdasarkan score, ambil top N
    validated.sort(key=lambda x: x["score"], reverse=True)
    result = validated[:num_clips * 2]
    logger.info(f"[HIGHLIGHTS] Validation done: {len(result)}/{len(highlights)} passed")
    return result


# ── Thread/Rate Limit Helpers ─────────────────────────────────────────

def _is_rate_limit_error(e: Exception) -> bool:
    """Detect if an exception is related to rate limiting (429, ResourceExhausted, etc.)."""
    err_name = e.__class__.__name__.lower()
    err_str = str(e).lower()
    if "ratelimit" in err_name or "rate_limit" in err_name or "resourceexhausted" in err_name:
        return True
    if "429" in err_str or "rate limit" in err_str or "throttled" in err_str or "resource_exhausted" in err_str:
        return True
    return False


def _process_chunk_with_retry(
    chunk_transcript: Dict,
    chunk_units_mapped: List[Dict],
    content_info: Dict,
    num_clips: int,
    llm_fn: LLMFn,
    start_val: float,
) -> List[Dict]:
    """Execute generate_highlights for a chunk with rate limit detection and exponential backoff + random jitter."""
    max_rate_limit_retries = 3
    backoff_factor = 2.0
    initial_delay = 5.0  # seconds, safer starting point for TPM reset windows
    
    for attempt in range(1, max_rate_limit_retries + 1):
        try:
            return generate_highlights(
                chunk_transcript, chunk_units_mapped, content_info, num_clips, llm_fn
            )
        except Exception as e:
            if _is_rate_limit_error(e) and attempt < max_rate_limit_retries:
                base_delay = initial_delay * (backoff_factor ** (attempt - 1))
                # Add random jitter (+/- 20% + small random offset) to prevent lockstep retry storms
                jitter = random.uniform(-0.2, 0.2) * base_delay + random.uniform(0.5, 1.5)
                delay = min(base_delay + jitter, 30.0)  # Max ceiling of 30 seconds
                
                logger.warning(
                    f"[CHUNK PROCESSOR] Rate limit hit on chunk starting at {start_val}s. "
                    f"Retrying in {delay:.1f}s... (Attempt {attempt}/{max_rate_limit_retries}) Error: {e}"
                )
                time.sleep(delay)
            else:
                # Re-raise standard/uncaught exceptions or when retries are exhausted
                raise e


# ── Main Entry Point ─────────────────────────────────────────────

def get_highlights(
    transcript: Dict,
    num_clips: int = 3,
    llm_fn: LLMFn | None = None,
    progress_callback: Optional[Callable[[float, str, str], None]] = None,
) -> Dict:
    """Temukan highlight viral dalam transkrip.
    
    Args:
        transcript: Hasil transkripsi.
        num_clips: Jumlah klip yang diinginkan.
        llm_fn: Fungsi LLM untuk pemanggilan model.
        progress_callback: Opsional — dipanggil dengan (pct, stage, message) untuk emit SSE progress.
    """
    def _cb(pct: float, stage: str, msg: str) -> None:
        if progress_callback:
            try:
                progress_callback(pct, stage, msg)
            except Exception:
                pass

    llm_fn = llm_fn or get_llm_fn()
    duration = transcript.get("duration", 0)
    
    # Sub-step 1: Content type & density
    _cb(37, "ANALYZE", "Mendeteksi tipe konten & kepadatan narasi…")
    content_info = detect_content_type(transcript, llm_fn=llm_fn)
    logger.info("[ANALYZE] Content type: %s, density: %s", content_info.get("content_type"), content_info.get("density"))
    
    # Sub-step 2: Narrative segmentation
    _cb(40, "ANALYZE", "Memetakan struktur narasi video…")
    narrative_units = segment_narrative(transcript, content_info, llm_fn=llm_fn)
    logger.info("[ANALYZE] Narrative units: %d", len(narrative_units))
    
    # Sub-step 3: Highlight generation
    _cb(44, "ANALYZE", "Mencari momen viral terbaik…")
    failed_chunks = []
    total_chunks = 1
    coverage_pct = 100
    
    if duration >= LONG_VIDEO_THRESHOLD:
        # Chunking untuk video panjang
        chunked_res = _generate_chunked(transcript, narrative_units, content_info, num_clips, llm_fn)
        highlights = chunked_res.get("highlights", [])
        failed_chunks = chunked_res.get("failed_chunks", [])
        total_chunks = chunked_res.get("total_chunks", 1)
        coverage_pct = chunked_res.get("coverage_pct", 100)
    else:
        highlights = generate_highlights(transcript, narrative_units, content_info, num_clips, llm_fn)
    
    _cb(49, "ANALYZE", f"Validasi {len(highlights)} highlight selesai")
    return {
        "highlights": highlights,
        "narrative_units": narrative_units,
        "failed_chunks": failed_chunks,
        "total_chunks": total_chunks,
        "coverage_pct": coverage_pct
    }


def _generate_chunked(
    transcript: Dict,
    narrative_units: List[Dict],
    content_info: Dict,
    num_clips: int,
    llm_fn: LLMFn,
) -> Dict:
    """Process long videos by chunking narrative units with a hybrid sequential-parallel strategy.
    
    Ensures prompt caching is warmed (if Anthropic is active) by processing the first chunk sequentially first.
    Subsequent chunks (or all chunks for other providers) are processed in parallel via ThreadPoolExecutor.
    """
    segments = transcript.get("segments", [])
    duration = transcript.get("duration", 0)
    
    # 1. Kumpulkan parameter pekerjaan chunk terlebih dahulu
    chunk_tasks = []
    start = 0
    while start < duration:
        end = min(start + CHUNK_SIZE_SECONDS, duration)
        
        # Dapatkan index segmen global yang masuk ke dalam chunk ini
        chunk_segment_indices = [
            i for i, s in enumerate(segments)
            if s["start"] >= start and s["end"] <= end + CHUNK_OVERLAP_SECONDS
        ]
        
        if chunk_segment_indices:
            # Bangun mapping relatif ↔ global
            relative_to_global_map = {rel_idx: glob_idx for rel_idx, glob_idx in enumerate(chunk_segment_indices)}
            global_to_relative_map = {glob_idx: rel_idx for rel_idx, glob_idx in enumerate(chunk_segment_indices)}
            
            # Saring segments untuk chunk
            chunk_segments = [segments[idx] for idx in chunk_segment_indices]
            
            # Saring unit narrative yang berada di dalam rentang segmen chunk, map segment ID ke lokal/relatif
            chunk_units_mapped = []
            for u in narrative_units:
                u_start = u["start_segment_id"]
                u_end = u["end_segment_id"]
                
                if u_start in global_to_relative_map and u_end in global_to_relative_map:
                    mapped_unit = u.copy()
                    mapped_unit["start_segment_id"] = global_to_relative_map[u_start]
                    mapped_unit["end_segment_id"] = global_to_relative_map[u_end]
                    chunk_units_mapped.append(mapped_unit)
            
            if chunk_units_mapped and chunk_segments:
                chunk_transcript = {"duration": end - start, "segments": chunk_segments}
                chunk_tasks.append((
                    chunk_transcript,
                    chunk_units_mapped,
                    start,
                    relative_to_global_map,
                    chunk_segment_indices
                ))
        
        start += CHUNK_SIZE_SECONDS - CHUNK_OVERLAP_SECONDS

    if not chunk_tasks:
        return {"highlights": [], "failed_chunks": [], "total_chunks": 0, "coverage_pct": 100}

    all_highlights = []
    failed_chunks = []
    total_chunks_count = len(chunk_tasks)
    is_anthropic = (LLM_PROVIDER or "openai").strip().lower() == "anthropic"

    # 2. Hybrid Execution Strategy:
    # Jika menggunakan Anthropic, proses chunk pertama secara sequential untuk warm-up prompt cache.
    # Jika OpenAI/Gemini, proses semua chunk secara paralel penuh untuk latensi minimal.
    tasks_to_parallel = chunk_tasks
    
    if is_anthropic:
        first_task = chunk_tasks[0]
        chunk_transcript, chunk_units_mapped, start_val, relative_to_global_map, chunk_segment_indices = first_task
        
        logger.info(f"[HIGHLIGHTS] Warm caching: Processing first chunk (start={start_val}s) sequentially...")
        try:
            first_highlights = _process_chunk_with_retry(
                chunk_transcript, chunk_units_mapped, content_info, num_clips, llm_fn, start_val
            )
            # Map back segment IDs dan timestamps relatif ke global asli
            for h in first_highlights:
                rel_start = h["start_segment_id"]
                rel_end = h["end_segment_id"]
                
                glob_start = relative_to_global_map.get(rel_start, chunk_segment_indices[0])
                glob_end = relative_to_global_map.get(rel_end, chunk_segment_indices[-1])
                
                h["start_segment_id"] = glob_start
                h["end_segment_id"] = glob_end
                h["start_time"] = segments[glob_start]["start"]
                h["end_time"] = segments[glob_end]["end"]
                
                all_highlights.append(h)
        except Exception as e:
            failed_chunks.append(start_val)
            logger.error(f"Failed to generate highlights for the first chunk (warm cache block): {e}")
            
        tasks_to_parallel = chunk_tasks[1:]

    # 3. Jalankan task paralel
    if tasks_to_parallel:
        mode_str = "parallel (cache warmed)" if is_anthropic else "parallel full"
        logger.info(f"[HIGHLIGHTS] Processing remaining {len(tasks_to_parallel)} chunks in {mode_str}...")
        
        with ThreadPoolExecutor(max_workers=min(len(tasks_to_parallel), HIGHLIGHT_MAX_WORKERS)) as executor:
            futures = {
                executor.submit(
                    _process_chunk_with_retry,
                    task[0], task[1], content_info, num_clips, llm_fn, task[2]
                ): task
                for task in tasks_to_parallel
            }
            
            for future in futures:
                task = futures[future]
                start_val, relative_to_global_map, chunk_segment_indices = task[2], task[3], task[4]
                try:
                    chunk_highlights = future.result()
                    # Map back segment IDs dan timestamps relatif ke global asli
                    for h in chunk_highlights:
                        rel_start = h["start_segment_id"]
                        rel_end = h["end_segment_id"]
                        
                        glob_start = relative_to_global_map.get(rel_start, chunk_segment_indices[0])
                        glob_end = relative_to_global_map.get(rel_end, chunk_segment_indices[-1])
                        
                        h["start_segment_id"] = glob_start
                        h["end_segment_id"] = glob_end
                        h["start_time"] = segments[glob_start]["start"]
                        h["end_time"] = segments[glob_end]["end"]
                        
                        all_highlights.append(h)
                except Exception as e:
                    failed_chunks.append(start_val)
                    logger.error(f"Failed to generate highlights for chunk starting at {start_val}s: {e}")

    # 4. Deteksi kegagalan sistemik (100% chunk gagal)
    if len(failed_chunks) == total_chunks_count:
        raise RuntimeError(
            f"Highlight generation failed completely: all {total_chunks_count} chunks failed to process due to API or validation errors."
        )
        
    coverage_pct = int(((total_chunks_count - len(failed_chunks)) / total_chunks_count) * 100) if total_chunks_count > 0 else 100

    return {
        "highlights": all_highlights,
        "failed_chunks": failed_chunks,
        "total_chunks": total_chunks_count,
        "coverage_pct": coverage_pct
    }


def chunk_transcript(transcript: Dict) -> List[Dict]:
    """Legacy function for compatibility."""
    return [transcript]

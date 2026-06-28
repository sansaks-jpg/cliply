"""Highlight and narrative unit validation.

Validates LLM-generated narrative units and highlights against transcript segments.
"""
import logging
import re
from typing import Dict, List, Optional

from .highlight_prompts import MAX_DURATION, MAX_OVERLAP_RATIO, MIN_DURATION

logger = logging.getLogger(__name__)


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


# ── Unit Validation ───────────────────────────────────────────────────

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

        # Forced Split jika unit melebihi MAX_DURATION
        unit_segments = list(range(start_id, end_id + 1))
        current_sub_start = start_id

        for seg_idx in unit_segments:
            seg_start = segments[current_sub_start]["start"]
            seg_end = segments[seg_idx]["end"]

            is_last = (seg_idx == end_id)
            if not is_last:
                next_seg_end = segments[seg_idx + 1]["end"]
                if next_seg_end - seg_start > MAX_DURATION:
                    validated.append({
                        "start_segment_id": current_sub_start,
                        "end_segment_id": seg_idx,
                        "start_time": seg_start,
                        "end_time": seg_end,
                        "topic": f"{u.get('topic', '')} (Part {len(validated)+1})",
                        "arc_type": arc_type,
                        "arc_complete": False,
                        "intensity": intensity,
                    })
                    current_sub_start = seg_idx + 1
            else:
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

    # Gap & Overlap Resolution
    validated.sort(key=lambda x: x["start_segment_id"])

    if validated[0]["start_segment_id"] > 0:
        validated[0]["start_segment_id"] = 0
        validated[0]["start_time"] = segments[0]["start"]

    cleaned = []
    for i in range(len(validated) - 1):
        curr_unit = validated[i]
        next_unit = validated[i+1]

        curr_end = curr_unit["end_segment_id"]
        next_start = next_unit["start_segment_id"]

        if curr_end >= next_start:
            new_end = max(curr_unit["start_segment_id"], next_start - 1)
            curr_unit["end_segment_id"] = new_end
            curr_unit["end_time"] = segments[new_end]["end"]
        elif curr_end < next_start - 1:
            new_end = next_start - 1
            curr_unit["end_segment_id"] = new_end
            curr_unit["end_time"] = segments[new_end]["end"]

        cleaned.append(curr_unit)
    cleaned.append(validated[-1])

    if cleaned[-1]["end_segment_id"] < n_segments - 1:
        cleaned[-1]["end_segment_id"] = n_segments - 1
        cleaned[-1]["end_time"] = segments[-1]["end"]

    logger.info(f"[UNITS] Validation done: {len(cleaned)} units clean and contiguous")
    return cleaned


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

        # 2. Check cumulative overlap
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

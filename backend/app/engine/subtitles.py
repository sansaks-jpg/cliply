"""Karaoke subtitle generator with pluggable animation styles (Strategy pattern).

Each style declares an ``animation`` key that dispatches to a builder function
in ``ANIMATION_BUILDERS``.  Adding a new style = adding a dict entry + a
builder — no if/elif chain to maintain.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ── Default paths ─────────────────────────────────────────────────

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DEFAULT_FONTS_DIR = _BACKEND_DIR / "fonts"

# ── ASS colours (decimal &HBBGGRR) ───────────────────────────────
_WHITE = "&H00FFFFFF"
_YELLOW = "&H0000FFFF"
_RED = "&H000000FF"
_BLACK = "&H00000000"
_GRAY = "&H00999999"
_CYAN = "&H00FFFF00"
_MAGENTA = "&H00FF00FF"
_DARK_GRAY = "&H00444444"


# ── Timestamp helpers ─────────────────────────────────────────────

def _cs(seconds: float) -> int:
    """Convert seconds to centiseconds (ASS \\k units)."""
    return max(0, int(seconds * 100))


def _fmt(seconds: Optional[float]) -> str:
    """Seconds → ``H:MM:SS.cc`` (ASS timestamp)."""
    s = max(0.0, seconds or 0.0)
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    cs = int((s % 1) * 100)
    return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"


def _seg_time(seg: Dict[str, Any], key: str) -> Optional[float]:
    """Read a timestamp from a segment, supporting both naming conventions."""
    val = seg.get(key)
    if val is not None:
        return float(val)
    val = seg.get(key.replace("_time", ""))
    if val is not None:
        return float(val)
    return None


def _split_words(text: str) -> List[str]:
    return text.strip().split()


def _clean_text(text: str) -> str:
    """Remove punctuation, keep only words and spaces."""
    text = re.sub(r'[.,!?;:\\\'"\[\](){}\-—]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _apply_case(text: str, case: str) -> str:
    """Apply text casing from style config."""
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    return text


def _estimate_text_width(text: str, font_size: int) -> float:
    """Estimate rendered text width in pixels based on character-specific weights."""
    total_width = 0.0
    for char in text:
        # Default weight for average characters
        weight = 0.55
        
        if char.isupper():
            if char in ("W", "M"):
                weight = 0.80
            elif char in ("I", "J", "L"):
                weight = 0.40
            else:
                weight = 0.65
        else:
            if char in ("w", "m"):
                weight = 0.70
            elif char in ("i", "l", "t", "j", "f", "r"):
                weight = 0.30
            elif char in (" ", "!", ".", ",", ";", ":", "'", '"', "-", "_", "(", ")"):
                weight = 0.25
                
        total_width += weight * font_size
    return total_width


def _wrap_and_balance(
    text: str,
    style: Dict[str, Any],
    play_res_x: int,
    font_size: int,
) -> List[str]:
    """Wrap text into lines that fit within max_line_width_ratio.

    Enforces max_lines and balances line widths to avoid orphans and widows.
    Returns a list of line strings (without ``\\N``).
    """
    max_ratio = style.get("max_line_width_ratio", 0.82)
    usable_width = play_res_x * max_ratio
    max_lines = style.get("max_lines", 2)

    words = text.strip().split()
    if not words:
        return [""]

    # Helper to estimate width of a list of words joined by spaces
    def get_width(w_list: List[str]) -> float:
        return _estimate_text_width(" ".join(w_list), font_size)

    # Case 1: Fits on 1 line or max_lines is 1
    if max_lines <= 1 or get_width(words) <= usable_width:
        if max_lines == 1:
            return [" ".join(words)]
        if get_width(words) <= usable_width:
            return [" ".join(words)]

    # Case 2: max_lines == 2. Try to split into 2 balanced lines.
    if max_lines == 2:
        best_split = 1
        min_max_width = float("inf")
        for i in range(1, len(words)):
            line1 = words[:i]
            line2 = words[i:]
            w1 = get_width(line1)
            w2 = get_width(line2)
            max_w = max(w1, w2)
            if max_w < min_max_width:
                min_max_width = max_w
                best_split = i
        
        if min_max_width <= usable_width:
            return [" ".join(words[:best_split]), " ".join(words[best_split:])]

    # Fallback/General: Greedy wrap
    lines: List[str] = []
    current: List[str] = []
    for w in words:
        candidate = current + [w]
        if get_width(candidate) > usable_width and current:
            lines.append(" ".join(current))
            current = [w]
        else:
            current = candidate
    if current:
        lines.append(" ".join(current))

    # Enforce max_lines limit by merging extra lines into the last line
    if len(lines) > max_lines:
        allowed_lines = lines[:max_lines - 1]
        remaining_words = []
        for line in lines[max_lines - 1:]:
            remaining_words.extend(line.split())
        allowed_lines.append(" ".join(remaining_words))
        return allowed_lines

    return lines


# ── Dialogue helper ───────────────────────────────────────────────

def _dialogue(
    start: float,
    end: float,
    text: str,
    color: Optional[str] = None,
    effect: str = "",
) -> str:
    colour_tag = f"{{\\c{color}}}" if color else ""
    effect_tag = f"{{\\{effect}}}" if effect else ""
    return (
        f"Dialogue: 0,{_fmt(start)},{_fmt(end)},Default,,0,0,0,,"
        f"{colour_tag}{effect_tag}{text}"
    )


# ── Adaptive Font Scaling & Wrapping ─────────────────────────────

def _find_adaptive_wrap(
    text: str,
    style: Dict[str, Any],
    play_res_x: int,
    base_font_size: int,
) -> Tuple[List[str], int]:
    """Finds the optimal line wrap and adaptive font size.

    Dynamically scales down the font size if the text is too long to fit
    within max_lines and max_line_width_ratio. If the text is very short (<= 2 words),
    allows scaling up slightly (up to 1.15x) for emphasis.
    
    Returns a tuple of (wrapped_lines, final_font_size).
    """
    max_ratio = style.get("max_line_width_ratio", 0.82)
    usable_width = play_res_x * max_ratio
    max_lines = style.get("max_lines", 2)

    words = text.strip().split()
    if not words:
        return [""], base_font_size

    # Scale up for very short text (1-2 words), start search higher
    max_font_size = base_font_size
    if len(words) <= 2:
        max_font_size = int(base_font_size * 1.15)
        
    min_font_size = max(14, int(base_font_size * 0.65))

    # Try font sizes from max_font_size down to min_font_size
    for fs in range(max_font_size, min_font_size - 1, -2):
        wrapped = _wrap_and_balance(text, style, play_res_x, fs)
        
        # Check if the result fits within max_lines AND no line exceeds usable_width
        fits = True
        if len(wrapped) > max_lines:
            fits = False
        else:
            for line in wrapped:
                if _estimate_text_width(line, fs) > usable_width:
                    fits = False
                    break
        
        if fits:
            return wrapped, fs

    # Fallback: force wrapped at min_font_size
    fallback_wrapped = _wrap_and_balance(text, style, play_res_x, min_font_size)
    return fallback_wrapped, min_font_size


# ── Animation builders ───────────────────────────────────────────
# Each returns a list[str] of Dialogue lines.


def _blur_prefix(style: Dict[str, Any]) -> str:
    """Return an inline \\blur<n> tag if the style has blur > 0, else empty string.

    ASS Shadow ≠ blur. The Shadow field in the style header creates a drop-shadow,
    not a Gaussian blur. To produce a real glow/blur, we must use the inline \\blur
    override tag (supported by libass ≥ 0.14 and most modern renderers).
    """
    blur = style.get("blur", 0)
    return f"{{\\blur{blur}}}" if blur else ""


def _build_karaoke_base(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
    tag_prefix: str = "\\kf",
) -> List[str]:
    """Helper to build standard karaoke-style ASS lines.

    Prevents timing drift by distributing modulo centiseconds perfectly.
    Prepends \\blur<n> if the style requests glow (blur > 0).
    """
    case = style.get("case", "normal")
    font_size = style.get("_font_size", 48)
    play_res_x = style.get("_play_res_x", 1080)
    blur_tag = _blur_prefix(style)
    lines: List[str] = []
    for seg in segments:
        t0 = _seg_time(seg, "start_time") or 0.0
        t1 = _seg_time(seg, "end_time") or 0.0
        text = (seg.get("text") or "").strip()
        text = _clean_text(text)
        if not text or t1 <= t0:
            continue
        # Find wrapped lines and adaptive font size
        wrapped, adaptive_fs = _find_adaptive_wrap(_apply_case(text, case), style, play_res_x, font_size)
        words = _apply_case(text, case).split()
        if not words:
            continue
        total_cs = _cs(t1 - t0)

        # Distribute centiseconds perfectly across words to prevent timing drift
        word_durations = []
        seg_words_data = seg.get("words", [])
        if seg_words_data and len(seg_words_data) == len(words):
            for w_data in seg_words_data:
                w_dur = _cs(w_data["end"] - w_data["start"])
                w_dur = min(w_dur, 80)  # Cap di 0.8s (80 cs) untuk menangani jeda panjang/noise
                word_durations.append(max(1, w_dur))
            
            # Normalisasi proporsional durasi agar jumlah totalnya cocok dengan total_cs
            sum_dur = sum(word_durations)
            if sum_dur != total_cs and sum_dur > 0:
                normalized = []
                for dur in word_durations:
                    norm_dur = (dur * total_cs) // sum_dur
                    normalized.append(max(1, norm_dur))
                # Tambahkan selisih pembagian bulat ke kata terakhir
                diff = total_cs - sum(normalized)
                if normalized:
                    normalized[-1] = max(1, normalized[-1] + diff)
                word_durations = normalized
        else:
            for i in range(len(words)):
                w_start = (i * total_cs) // len(words)
                w_end = ((i + 1) * total_cs) // len(words)
                word_durations.append(max(1, w_end - w_start))

        result_lines = []
        idx = 0
        for wline in wrapped:
            wcount = len(wline.split())
            chunk_words = words[idx:idx + wcount]
            chunk_durations = word_durations[idx:idx + wcount]
            idx += wcount
            parts = " ".join(f"{{{tag_prefix}{dur}}}{w}" for w, dur in zip(chunk_words, chunk_durations))
            result_lines.append(parts)

        diag_text = "\\N".join(result_lines)
        # Apply adaptive font size override if needed
        if adaptive_fs != font_size:
            diag_text = f"{{\\fs{adaptive_fs}}}" + diag_text
        # Prepend blur tag (ASS inline \blur — real Gaussian glow, not Shadow)
        if blur_tag:
            diag_text = blur_tag + diag_text
        lines.append(_dialogue(t0, t1, diag_text, color=None))
    return lines


def build_karaoke_fill(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Karaoke fill — per-word instant colour pop using \\k.

    libass switches the word colour from SecondaryColour (inactive) to PrimaryColour (active) 
    instantly at the start of the word duration, matching the frontend pop behavior.
    """
    return _build_karaoke_base(segments, style, "\\k")


def build_karaoke_sweep(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Karaoke sweep — Refactored to use dual-layer static blur glow for maximum CPU performance.
    
    Instead of animating \\blur frame-by-frame (which causes extreme CPU lag in libass),
    this implementation duplicates each dialogue event:
    1. Layer 0 (Glow Layer): A background layer with a static, non-animated \\blur8.
       We animate the transparency (\\alpha) of the active word to create the pulsing highlight.
    2. Layer 1 (Sharp Text Layer): A sharp foreground layer on top with \\blur0.
       Changes color instantly per word using standard \\k.
    """
    case = style.get("case", "normal")
    font_size = style.get("_font_size", 48)
    play_res_x = style.get("_play_res_x", 1080)
    
    glow_color = style.get("highlight_color", _MAGENTA)
    primary_color = style.get("primary_color", _CYAN)
    outline_color = style.get("outline_color", _BLACK)
    
    lines: List[str] = []
    
    for seg in segments:
        t0 = _seg_time(seg, "start_time") or 0.0
        t1 = _seg_time(seg, "end_time") or 0.0
        text = (seg.get("text") or "").strip()
        text = _clean_text(text)
        if not text or t1 <= t0:
            continue
            
        wrapped, adaptive_fs = _find_adaptive_wrap(_apply_case(text, case), style, play_res_x, font_size)
        words = _apply_case(text, case).split()
        if not words:
            continue
            
        total_cs = _cs(t1 - t0)
        flash_dur = min(20, (total_cs * 10) // (len(words) * 2))  # centiseconds, max 20 cs (200ms)
        
        # Calculate word durations
        word_durations = []
        seg_words_data = seg.get("words", [])
        if seg_words_data and len(seg_words_data) == len(words):
            for w_data in seg_words_data:
                w_dur = _cs(w_data["end"] - w_data["start"])
                w_dur = min(w_dur, 80)
                word_durations.append(max(1, w_dur))
            
            sum_dur = sum(word_durations)
            if sum_dur != total_cs and sum_dur > 0:
                normalized = []
                for dur in word_durations:
                    norm_dur = (dur * total_cs) // sum_dur
                    normalized.append(max(1, norm_dur))
                diff = total_cs - sum(normalized)
                if normalized:
                    normalized[-1] = max(1, normalized[-1] + diff)
                word_durations = normalized
        else:
            for i in range(len(words)):
                w_start = (i * total_cs) // len(words)
                w_end = ((i + 1) * total_cs) // len(words)
                word_durations.append(max(1, w_end - w_start))
                
        # ── LAYER 0: GLOW BACKGROUND ──
        glow_lines = []
        idx = 0
        cumulative_cs = 0
        for wline in wrapped:
            wcount = len(wline.split())
            chunk_words = words[idx:idx + wcount]
            chunk_durations = word_durations[idx:idx + wcount]
            idx += wcount
            parts = []
            for w, dur in zip(chunk_words, chunk_durations):
                t_start = cumulative_cs
                t_mid = t_start + flash_dur
                t_end = t_start + flash_dur * 2
                
                glow_tag = (
                    f"{{\\alpha&HFF&"
                    f"\\t({t_start * 10},{t_mid * 10},\\alpha&H00&)"
                    f"\\t({t_mid * 10},{t_end * 10},\\alpha&HFF&)}}"
                )
                parts.append(f"{glow_tag}{w}")
                cumulative_cs += dur
            glow_lines.append(" ".join(parts))
            
        glow_text = "\\N".join(glow_lines)
        if adaptive_fs != font_size:
            glow_text = f"{{\\fs{adaptive_fs}}}" + glow_text
        glow_text = f"{{\\blur8\\1c{glow_color}\\3c{glow_color}\\bord6}}" + glow_text
        
        lines.append(f"Dialogue: 0,{_fmt(t0)},{_fmt(t1)},Default,,0,0,0,," + glow_text)
        
        # ── LAYER 1: SHARP FOREGROUND ──
        sharp_lines = []
        idx = 0
        for wline in wrapped:
            wcount = len(wline.split())
            chunk_words = words[idx:idx + wcount]
            chunk_durations = word_durations[idx:idx + wcount]
            idx += wcount
            parts = []
            for w, dur in zip(chunk_words, chunk_durations):
                parts.append(f"{{\\k{dur}}}{w}")
            sharp_lines.append(" ".join(parts))
            
        sharp_text = "\\N".join(sharp_lines)
        if adaptive_fs != font_size:
            sharp_text = f"{{\\fs{adaptive_fs}}}" + sharp_text
        sharp_text = f"{{\\blur0\\1c{glow_color}\\2c{primary_color}\\3c{outline_color}}}" + sharp_text
        
        lines.append(f"Dialogue: 1,{_fmt(t0)},{_fmt(t1)},Default,,0,0,0,," + sharp_text)
        
    return lines


def build_fade_in_word(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Fade-in per word — each word appears with a short alpha transition.

    All words in one Dialogue line, avoiding overlapping center alignments.
    """
    fade_ms = style.get("fade_ms", 150)
    case = style.get("case", "normal")
    font_size = style.get("_font_size", 48)
    play_res_x = style.get("_play_res_x", 1080)
    fade_alpha_from = style.get("fade_alpha_from", "&HFF&")
    lines: List[str] = []
    for seg in segments:
        t0 = _seg_time(seg, "start_time") or 0.0
        t1 = _seg_time(seg, "end_time") or 0.0
        text = (seg.get("text") or "").strip()
        text = _clean_text(text)
        if not text or t1 <= t0:
            continue
        wrapped, adaptive_fs = _find_adaptive_wrap(_apply_case(text, case), style, play_res_x, font_size)
        words = _apply_case(text, case).split()
        if not words:
            continue
        seg_words_data = seg.get("words", [])
        duration = t1 - t0
        per_word = duration / len(words)
        
        result_lines = []
        idx = 0
        for wline in wrapped:
            wcount = len(wline.split())
            chunk_words = words[idx:idx + wcount]
            parts = []
            for j, w in enumerate(chunk_words):
                overall_idx = idx + j
                if seg_words_data and len(seg_words_data) == len(words):
                    w_data = seg_words_data[overall_idx]
                    ms_offset = max(0, int((w_data["start"] - t0) * 1000))
                else:
                    ms_offset = int(overall_idx * per_word * 1000)
                parts.append(
                    f"{{\\alpha{fade_alpha_from}\\t({ms_offset},{ms_offset + fade_ms},\\alpha&H00&)}}{w}"
                )
            idx += wcount
            result_lines.append(" ".join(parts))
        
        diag_text = "\\N".join(result_lines)
        if adaptive_fs != font_size:
            diag_text = f"{{\\fs{adaptive_fs}}}" + diag_text
        lines.append(_dialogue(t0, t1, diag_text, color=None))
    return lines


def build_word_popup(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Pop-up per word — each word scales in from small with a descelerated bounce (ease-out).

    All words in one Dialogue line, avoiding overlapping center alignments.
    """
    pop_from = style.get("pop_scale_from", 70)
    pop_dur = style.get("pop_duration_ms", 200)
    case = style.get("case", "normal")
    font_size = style.get("_font_size", 48)
    play_res_x = style.get("_play_res_x", 1080)
    pop_alpha_from = style.get("pop_alpha_from", "&HFF&")
    lines: List[str] = []
    for seg in segments:
        t0 = _seg_time(seg, "start_time") or 0.0
        t1 = _seg_time(seg, "end_time") or 0.0
        text = (seg.get("text") or "").strip()
        text = _clean_text(text)
        if not text or t1 <= t0:
            continue
        wrapped, adaptive_fs = _find_adaptive_wrap(_apply_case(text, case), style, play_res_x, font_size)
        words = _apply_case(text, case).split()
        if not words:
            continue
        seg_words_data = seg.get("words", [])
        duration = t1 - t0
        per_word = duration / len(words)
        
        result_lines = []
        idx = 0
        for wline in wrapped:
            wcount = len(wline.split())
            chunk_words = words[idx:idx + wcount]
            parts = []
            for j, w in enumerate(chunk_words):
                overall_idx = idx + j
                if seg_words_data and len(seg_words_data) == len(words):
                    w_data = seg_words_data[overall_idx]
                    ms_offset = max(0, int((w_data["start"] - t0) * 1000))
                else:
                    ms_offset = int(overall_idx * per_word * 1000)
                # Gunakan akselerasi 0.5 di tag \\t untuk efek deselerasi (ease-out)
                parts.append(
                    f"{{\\alpha{pop_alpha_from}\\fscx{pop_from}\\fscy{pop_from}"
                    f"\\t({ms_offset},{ms_offset + 1},\\alpha&H00&)"
                    f"\\t({ms_offset},{ms_offset + pop_dur},0.5,\\fscx100\\fscy100)}}{w}"
                )
            idx += wcount
            result_lines.append(" ".join(parts))
            
        diag_text = "\\N".join(result_lines)
        if adaptive_fs != font_size:
            diag_text = f"{{\\fs{adaptive_fs}}}" + diag_text
        lines.append(_dialogue(t0, t1, diag_text, color=None))
    return lines


def build_word_pop_scale(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Word pop scale — one word visible at a time, pops in from scale with desceleration (ease-out).

    Unlike word_popup (all words visible, each animates in), this shows only
    the active word (words_per_chunk=1) at center position.
    """
    pop_from = style.get("pop_scale_from", 70)
    pop_dur = style.get("pop_duration_ms", 180)
    case = style.get("case", "normal")
    lines: List[str] = []
    for seg in segments:
        t0 = _seg_time(seg, "start_time") or 0.0
        t1 = _seg_time(seg, "end_time") or 0.0
        text = (seg.get("text") or "").strip()
        text = _clean_text(text)
        if not text or t1 <= t0:
            continue
        words = _apply_case(text, case).split()
        if not words:
            continue
        seg_words_data = seg.get("words", [])
        duration = t1 - t0
        per_word = duration / len(words)
        for i, w in enumerate(words):
            if seg_words_data and len(seg_words_data) == len(words):
                ws = seg_words_data[i]["start"]
                we = seg_words_data[i]["end"]
            else:
                ws = t0 + i * per_word
                we = t0 + (i + 1) * per_word
            # Gunakan akselerasi 0.5 di tag \\t untuk efek deselerasi (ease-out)
            lines.append(
                _dialogue(
                    ws, we,
                    f"{{\\fscx{pop_from}\\fscy{pop_from}\\t(0,{pop_dur},0.5,\\fscx100\\fscy100)}}{w}"
                )
            )
    return lines


def build_word_box_highlight(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Word box highlight — Now refactored to use safe inline text coloring.
    
    Instead of using absolute positioning \\pos() and drawing dynamic borders
    which breaks text wrapping and layout, this implementation keeps the text in
    a single dialogue line and uses inline color tags (e.g. {\\1c<highlight>}) 
    to highlight the active word while keeping other words in the inactive color.
    """
    active_color = style.get("box_color", "&H0076E600")
    inactive_color = style.get("inactive_color", "&H00EEEEEE")
    case = style.get("case", "normal")
    font_size = style.get("_font_size", 48)
    play_res_x = style.get("_play_res_x", 1080)
    
    lines: List[str] = []
    for seg in segments:
        t0 = _seg_time(seg, "start_time") or 0.0
        t1 = _seg_time(seg, "end_time") or 0.0
        text = (seg.get("text") or "").strip()
        text = _clean_text(text)
        if not text or t1 <= t0:
            continue
            
        wrapped, adaptive_fs = _find_adaptive_wrap(_apply_case(text, case), style, play_res_x, font_size)
        words = _apply_case(text, case).split()
        if not words:
            continue
            
        seg_words_data = seg.get("words", [])
        duration = t1 - t0
        per_word = duration / len(words)
        
        for i, w in enumerate(words):
            if seg_words_data and len(seg_words_data) == len(words):
                ws = seg_words_data[i]["start"]
                we = seg_words_data[i]["end"]
            else:
                ws = t0 + i * per_word
                we = t0 + (i + 1) * per_word
                
            ws = max(t0, min(t1, ws))
            we = max(t0, min(t1, we))
            if we <= ws:
                we = ws + 0.01

            # Reconstruct sentence wrapping inline color tags around the active word
            words_styled = []
            idx = 0
            for wline in wrapped:
                line_words = wline.split()
                line_parts = []
                for lw in line_words:
                    if idx == i:
                        line_parts.append(f"{{\\1c{active_color}}}{lw}{{\\1c{inactive_color}}}")
                    else:
                        line_parts.append(lw)
                    idx += 1
                words_styled.append(" ".join(line_parts))
                
            diag_text = "\\N".join(words_styled)
            if adaptive_fs != font_size:
                diag_text = f"{{\\fs{adaptive_fs}}}" + diag_text
            
            diag_text = f"{{\\1c{inactive_color}}}" + diag_text
            lines.append(_dialogue(ws, we, diag_text, color=None))
            
            # Gap before the first word
            if i == 0 and ws > t0:
                words_all_inactive = []
                for wline in wrapped:
                    words_all_inactive.append(wline)
                inactive_text = f"{{\\1c{inactive_color}}}" + "\\N".join(words_all_inactive)
                if adaptive_fs != font_size:
                    inactive_text = f"{{\\fs{adaptive_fs}}}" + inactive_text
                lines.insert(0, _dialogue(t0, ws, inactive_text, color=None))
                
            # Gap after the last word
            if i == len(words) - 1 and we < t1:
                words_all_inactive = []
                for wline in wrapped:
                    words_all_inactive.append(wline)
                inactive_text = f"{{\\1c{inactive_color}}}" + "\\N".join(words_all_inactive)
                if adaptive_fs != font_size:
                    inactive_text = f"{{\\fs{adaptive_fs}}}" + inactive_text
                lines.append(_dialogue(we, t1, inactive_text, color=None))
    return lines


# ── Style registry ────────────────────────────────────────────────

ANIMATION_BUILDERS: Dict[str, Callable] = {
    "karaoke_fill": build_karaoke_fill,
    "karaoke_sweep": build_karaoke_sweep,
    "fade_in_word": build_fade_in_word,
    "word_popup": build_word_popup,
    "word_pop_scale": build_word_pop_scale,
    "word_box_highlight": build_word_box_highlight,
}

STYLES: Dict[str, Dict[str, Any]] = {
    # ── Original styles (kept) ────────────────────────────────────
    "viral-bold": {
        "animation": "karaoke_fill",
        "font": "Montserrat", "case": "upper",
        "primary_color": "&H00FFFFFF",
        "highlight_color": "&H0000FFFF",
        "outline_color": "&H00000000",
        "outline_width": 4, "blur": 0,
        "margin_v_ratio": 0.26, "margin_h_ratio": 0.09,
        "max_line_width_ratio": 0.82, "max_lines": 2,
        "font_size_ratio": 0.042, "bold": True,
    },
    "minimalist": {
        "animation": "fade_in_word",
        "font": "Helvetica", "case": "normal",
        "font_size_ratio": 0.035,
        "primary_color": _WHITE,
        "outline_color": _DARK_GRAY,
        "outline_width": 1,
        "margin_v_ratio": 0.22, "margin_h_ratio": 0.09,
        "max_line_width_ratio": 0.82,
        "bold": False,
        "fade_ms": 150,
    },
    "neon-glow": {
        "animation": "karaoke_sweep",
        "font": "Montserrat", "case": "normal",
        "font_size_ratio": 0.042,
        "primary_color": _CYAN,
        "highlight_color": _MAGENTA,
        "outline_color": _BLACK,
        "outline_width": 4,
        "margin_v_ratio": 0.26, "margin_h_ratio": 0.09,
        "max_line_width_ratio": 0.82,
        "bold": True,
    },
    "classic-popup": {
        "animation": "word_popup",
        "font": "Helvetica", "case": "normal",
        "font_size_ratio": 0.040,
        "primary_color": _WHITE,
        "highlight_color": _YELLOW,
        "outline_color": _BLACK,
        "outline_width": 2,
        "margin_v_ratio": 0.26, "margin_h_ratio": 0.09,
        "max_line_width_ratio": 0.82,
        "bold": True,
        "pop_scale_from": 70,
        "pop_duration_ms": 200,
    },
    # ── New styles (from user spec) ───────────────────────────────
    "word-pop": {
        "animation": "word_pop_scale",
        "font": "Plus Jakarta Sans", "case": "upper",
        "primary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "outline_width": 5, "blur": 0,
        "pop_scale_from": 70, "pop_duration_ms": 180,
        "margin_v_ratio": 0.26, "margin_h_ratio": 0.09,
        "max_line_width_ratio": 0.82, "max_lines": 1, "words_per_chunk": 1,
        "font_size_ratio": 0.048, "bold": True,
    },
    "clean-minimal": {
        "animation": "fade_in_word",
        "font": "Helvetica", "case": "lower",
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00CCCCCC",
        "outline_color": "&H00000000", "outline_width": 0,
        "shadow": 2,  # Tambahkan Drop Shadow statis untuk keterbacaan di background terang
        "fade_ms": 150,
        "margin_v_ratio": 0.22, "margin_h_ratio": 0.09,
        "max_line_width_ratio": 0.82, "max_lines": 1,
        "font_size_ratio": 0.035, "bold": False,
    },
    "highlight-box": {
        "animation": "word_box_highlight",
        "font": "Plus Jakarta Sans", "case": "normal",
        "primary_color": "&H00FFFFFF",
        "box_color": "&H0076E600",
        "inactive_color": "&H00EEEEEE",
        "box_border_width": 14,
        "outline_color": "&H00000000", "outline_width": 0,
        "shadow": 1.5,  # Tambahkan bayangan tipis
        "margin_v_ratio": 0.26, "margin_h_ratio": 0.09,
        "max_line_width_ratio": 0.82, "max_lines": 2,
        "font_size_ratio": 0.042, "bold": True,
    },
    "neon-gradient": {
        "animation": "karaoke_fill",
        "font": "Montserrat", "case": "upper",
        "primary_color": "&H00FFF000",
        "highlight_color": "&H00E500FF",
        "outline_color": "&H00FFF000",
        "outline_width": 2, "blur": 4,
        "margin_v_ratio": 0.26, "margin_h_ratio": 0.09,
        "max_line_width_ratio": 0.82, "max_lines": 2,
        "font_size_ratio": 0.042, "bold": True,
    },
    # ── TikTok-style (remotion-dev/template-tiktok) ─────────────────
    "tiktok": {
        "animation": "karaoke_fill",
        "font": "Plus Jakarta Sans", "case": "upper",
        "primary_color": "&H00FFFFFF",
        "highlight_color": "&H0008E539",
        "outline_color": "&H00000000",
        "outline_width": 8,  # Kurangi outline dari 20 ke 8 agar tidak menabrak spasi antar kata
        "blur": 0,
        "margin_v_ratio": 0.18, "margin_h_ratio": 0.05,
        "max_line_width_ratio": 0.90, "max_lines": 2,
        "font_size_ratio": 0.062, "bold": True,
        "words_per_chunk": 4,
    },
}

AVAILABLE_STYLES = list(STYLES.keys())
DEFAULT_STYLE = "viral-bold"


# ── ASS file generation ───────────────────────────────────────────


def _header(style: Dict[str, Any], play_res_x: int, play_res_y: int) -> str:
    bold = -1 if style.get("bold") else 0
    font_name = style["font"]
    font_size = max(20, int(play_res_y * style["font_size_ratio"]))
    margin_v = round(play_res_y * style.get("margin_v_ratio", 0.15))
    margin_h = round(play_res_x * style.get("margin_h_ratio", 0.09))

    # Gunakan shadow dari style config (default 0)
    shadow = style.get("shadow", 0)
    
    # Warna bayangan semi-transparan (default hitam 50% transparan = &H80000000)
    back_color = style.get("back_color", "&H80000000")

    anim = style.get("animation", "karaoke_fill")
    if anim in ("karaoke_fill", "karaoke_sweep", "word_box_highlight"):
        # For karaoke: Secondary = inactive color (white), Primary = active/highlight color.
        # libass advances \kf fill from Secondary→Primary as each word is spoken.
        primary_color = style.get("highlight_color", _YELLOW)
        secondary_color = style.get("primary_color", _WHITE)
    else:
        primary_color = style.get("primary_color", _WHITE)
        secondary_color = style.get("secondary_color", style.get("highlight_color", _YELLOW))

    return (
        "[Script Info]\n"
        "Title: clip-ai subtitles\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_res_x}\n"
        f"PlayResY: {play_res_y}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},"
        f"{primary_color},{secondary_color},"
        f"{style['outline_color']},{back_color},"
        f"{bold},0,0,0,100,100,0,0,1,"
        f"{style['outline_width']},{shadow},2,{margin_h},{margin_h},{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _chunk_segments(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Split long transcript segments into smaller chunks to prevent massive text blocks on screen.

    Uses words_per_chunk if specified, otherwise targets 3-4 words for 1-line layouts
    and 6-7 words for 2-line layouts.
    """
    max_lines = style.get("max_lines", 2)
    words_per_chunk = style.get("words_per_chunk")
    
    if words_per_chunk is not None:
        chunk_size = max(1, words_per_chunk)
    else:
        chunk_size = 3 if max_lines == 1 else 5

    chunked: List[Dict[str, Any]] = []
    for seg in segments:
        t0 = _seg_time(seg, "start_time") or 0.0
        t1 = _seg_time(seg, "end_time") or 0.0
        text = (seg.get("text") or "").strip()
        text = _clean_text(text)
        if not text or t1 <= t0:
            continue
            
        seg_words_data = seg.get("words", [])
        original_words = text.split()
        
        if seg_words_data:
            if len(seg_words_data) != len(original_words):
                log.warning(
                    "word count mismatch di segmen t=%.2f-%.2f: text=%d kata, model=%d kata. "
                    "Menyelaraskan teks dengan data kata model. Text: %r",
                    t0, t1, len(original_words), len(seg_words_data), text
                )
            words = [w["word"] for w in seg_words_data]
            text = " ".join(words)
            n_words = len(words)
        else:
            words = original_words
            n_words = len(words)
            
        if not words:
            continue
            
        duration = t1 - t0
        per_word = duration / n_words
        
        # Safety cap: cegah karaoke terlalu lambat akibat hallucination timestamp panjang
        MAX_SEC_PER_WORD = 0.8
        if per_word > MAX_SEC_PER_WORD:
            log.warning("per_word=%.2fs > %.2fs for seg t=%.2f-%.2f, capping", per_word, MAX_SEC_PER_WORD, t0, t1)
            per_word = MAX_SEC_PER_WORD
        
        for i in range(0, n_words, chunk_size):
            chunk_words = words[i:i + chunk_size]
            
            # Jika ada data kata tingkat kata yang presisi dari model
            if seg_words_data and len(seg_words_data) == n_words:
                c_start = max(t0, seg_words_data[i]["start"])
                chunk_end_idx = min(n_words, i + chunk_size) - 1
                c_end = min(t1, seg_words_data[chunk_end_idx]["end"])
                # Clamp waktu kata individual juga agar berada dalam rentang [c_start, c_end]
                chunk_words_data = []
                for w_data in seg_words_data[i:i + chunk_size]:
                    w_start = max(c_start, min(c_end, w_data["start"]))
                    w_end = max(c_start, min(c_end, w_data["end"]))
                    if w_end > w_start:
                        chunk_words_data.append({**w_data, "start": w_start, "end": w_end})
                    else:
                        chunk_words_data.append({**w_data, "start": w_start, "end": w_start + 0.01})
            else:
                c_start = t0 + i * per_word
                c_end = t0 + min(n_words, i + chunk_size) * per_word
                chunk_words_data = []
            
            new_seg = dict(seg)
            new_seg["start"] = c_start
            new_seg["end"] = c_end
            new_seg["start_time"] = c_start
            new_seg["end_time"] = c_end
            new_seg["text"] = " ".join(chunk_words)
            if chunk_words_data:
                new_seg["words"] = chunk_words_data
            chunked.append(new_seg)
            
    return chunked


def _resolve_overlaps(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure no two adjacent segments overlap in time."""
    if not segments:
        return []
    
    # Deep copy segments to avoid modifying the original list in place
    resolved = [dict(seg) for seg in segments]
    
    for i in range(len(resolved) - 1):
        curr_end = _seg_time(resolved[i], "end_time") or 0.0
        next_start = _seg_time(resolved[i+1], "start_time") or 0.0
        
        if curr_end > next_start:
            curr_start = _seg_time(resolved[i], "start_time") or 0.0
            if next_start >= curr_start:
                resolved[i]["end_time"] = next_start
                resolved[i]["end"] = next_start
            else:
                resolved[i+1]["start_time"] = curr_end
                resolved[i+1]["start"] = curr_end
                if resolved[i+1]["start_time"] >= (resolved[i+1].get("end_time") or resolved[i+1].get("end") or 0.0):
                    log.warning(
                        "Segmen %d (%r) sepenuhnya termakan overlap-resolution, teks berpotensi hilang. start=%.2f, end=%.2f",
                        i + 1,
                        resolved[i+1].get("text", ""),
                        resolved[i+1]["start_time"],
                        resolved[i+1].get("end_time") or resolved[i+1].get("end")
                    )
                
    return resolved


def _hex_to_ass(hex_color: str) -> str:
    """Convert hex color (#RRGGBB or RRGGBB) to ASS color format (&H00BBGGRR)."""
    if not hex_color:
        return ""
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) == 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        return f"&H00{b.upper()}{g.upper()}{r.upper()}"
    elif len(hex_color) == 3:
        r, g, b = hex_color[0], hex_color[1], hex_color[2]
        return f"&H00{b.upper()}{b.upper()}{g.upper()}{g.upper()}{r.upper()}{r.upper()}"
    return hex_color


def generate_ass(
    segments: List[Dict[str, Any]],
    style_key: str,
    output_path: str,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    fonts_dir: Optional[str] = None,
    subtitle_font: Optional[str] = None,
    subtitle_color_primary: Optional[str] = None,
    subtitle_color_highlight: Optional[str] = None,
) -> str:
    """Generate a .ass subtitle file with the given animation style.

    Args:
        segments: Transcript segments (each with ``text``, ``start_time``/``start``,
                  ``end_time``/``end``).
        style_key: Key in :data:`STYLES` (e.g. ``"viral-bold"``).
        output_path: Where to write the ``.ass`` file.
        play_res_x: ASS PlayResX — should match output video width.
        play_res_y: ASS PlayResY — should match output video height.
        fonts_dir: Optional path to a directory containing font files.
        subtitle_font: Optional custom font override.
        subtitle_color_primary: Optional custom primary/base color override (#RRGGBB).
        subtitle_color_highlight: Optional custom highlight/active color override (#RRGGBB).

    Returns:
        The absolute path of the generated file.
    """
    if style_key not in STYLES:
        log.warning("Unknown subtitle style %r, falling back to %r", style_key, DEFAULT_STYLE)
        style_key = DEFAULT_STYLE

    style = dict(STYLES[style_key])
    
    # Apply custom overrides
    if subtitle_font:
        style["font"] = subtitle_font
    if subtitle_color_primary:
        style["primary_color"] = _hex_to_ass(subtitle_color_primary)
    if subtitle_color_highlight:
        ass_highlight = _hex_to_ass(subtitle_color_highlight)
        style["highlight_color"] = ass_highlight
        style["secondary_color"] = ass_highlight

    font_size = max(20, int(play_res_y * style["font_size_ratio"]))
    style = {**style, "_font_size": font_size, "_play_res_x": play_res_x, "_play_res_y": play_res_y}
    
    # Resolve overlapping segment timings first
    resolved_segments = _resolve_overlaps(segments)
    
    # Split segments into optimal chunks before building dialogue lines
    chunked_segments = _chunk_segments(resolved_segments, style)
    
    builder = ANIMATION_BUILDERS[style["animation"]]
    dialogue_lines = builder(chunked_segments, style)
    header = _header(style, play_res_x, play_res_y)
    content = header + "\n".join(dialogue_lines) + "\n"

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write(content)

    log.info("Generated ASS subtitle: %s (style=%s, %d lines)", output_path, style_key, len(dialogue_lines))
    return os.path.abspath(output_path)

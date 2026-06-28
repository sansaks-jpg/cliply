"""Karaoke subtitle generator with pluggable animation styles.

Submodules:
  - subtitle_styles: style definitions and animation builder registry
  - subtitle_builders: animation builder implementations
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .subtitle_styles import STYLES, AVAILABLE_STYLES, DEFAULT_STYLE, _get_builders

log = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DEFAULT_FONTS_DIR = _BACKEND_DIR / "fonts"


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
    """Wrap text into lines that fit within max_line_width_ratio."""
    max_ratio = style.get("max_line_width_ratio", 0.82)
    usable_width = play_res_x * max_ratio
    max_lines = style.get("max_lines", 2)

    words = text.strip().split()
    if not words:
        return [""]

    def get_width(w_list: List[str]) -> float:
        return _estimate_text_width(" ".join(w_list), font_size)

    if max_lines <= 1 or get_width(words) <= usable_width:
        if max_lines == 1:
            return [" ".join(words)]
        if get_width(words) <= usable_width:
            return [" ".join(words)]

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

    if len(lines) > max_lines:
        allowed_lines = lines[:max_lines - 1]
        remaining_words = []
        for line in lines[max_lines - 1:]:
            remaining_words.extend(line.split())
        allowed_lines.append(" ".join(remaining_words))
        return allowed_lines

    return lines


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


def _find_adaptive_wrap(
    text: str,
    style: Dict[str, Any],
    play_res_x: int,
    base_font_size: int,
) -> tuple:
    """Finds the optimal line wrap and adaptive font size."""
    max_ratio = style.get("max_line_width_ratio", 0.82)
    usable_width = play_res_x * max_ratio
    max_lines = style.get("max_lines", 2)

    words = text.strip().split()
    if not words:
        return [""], base_font_size

    max_font_size = base_font_size
    if len(words) <= 2:
        max_font_size = int(base_font_size * 1.15)

    min_font_size = max(14, int(base_font_size * 0.65))

    for fs in range(max_font_size, min_font_size - 1, -2):
        wrapped = _wrap_and_balance(text, style, play_res_x, fs)
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

    fallback_wrapped = _wrap_and_balance(text, style, play_res_x, min_font_size)
    return fallback_wrapped, min_font_size


# ── Chunk & Overlap Resolution ────────────────────────────────────

def _chunk_segments(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Split long transcript segments into smaller chunks to prevent massive text blocks on screen."""
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

        MAX_SEC_PER_WORD = 0.8
        if per_word > MAX_SEC_PER_WORD:
            log.warning("per_word=%.2fs > %.2fs for seg t=%.2f-%.2f, capping", per_word, MAX_SEC_PER_WORD, t0, t1)
            per_word = MAX_SEC_PER_WORD

        for i in range(0, n_words, chunk_size):
            chunk_words = words[i:i + chunk_size]

            if seg_words_data and len(seg_words_data) == n_words:
                c_start = max(t0, seg_words_data[i]["start"])
                chunk_end_idx = min(n_words, i + chunk_size) - 1
                c_end = min(t1, seg_words_data[chunk_end_idx]["end"])
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


# ── ASS file generation ───────────────────────────────────────────


def _header(style: Dict[str, Any], play_res_x: int, play_res_y: int) -> str:
    bold = -1 if style.get("bold") else 0
    font_name = style["font"]
    font_size = max(20, int(play_res_y * style["font_size_ratio"]))
    margin_v = round(play_res_y * style.get("margin_v_ratio", 0.15))
    margin_h = round(play_res_x * style.get("margin_h_ratio", 0.09))

    shadow = style.get("shadow", 0)
    back_color = style.get("back_color", "&H80000000")

    anim = style.get("animation", "karaoke_fill")
    if anim in ("karaoke_fill", "karaoke_sweep", "word_box_highlight"):
        primary_color = style.get("highlight_color", "&H0000FFFF")
        secondary_color = style.get("primary_color", "&H00FFFFFF")
    else:
        primary_color = style.get("primary_color", "&H00FFFFFF")
        secondary_color = style.get("secondary_color", style.get("highlight_color", "&H0000FFFF"))

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
    """Generate a .ass subtitle file with the given animation style."""
    if style_key not in STYLES:
        log.warning("Unknown subtitle style %r, falling back to %r", style_key, DEFAULT_STYLE)
        style_key = DEFAULT_STYLE

    style = dict(STYLES[style_key])

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

    resolved_segments = _resolve_overlaps(segments)
    chunked_segments = _chunk_segments(resolved_segments, style)

    builders = _get_builders()
    builder = builders[style["animation"]]
    dialogue_lines = builder(chunked_segments, style)
    header = _header(style, play_res_x, play_res_y)
    content = header + "\n".join(dialogue_lines) + "\n"

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write(content)

    log.info("Generated ASS subtitle: %s (style=%s, %d lines)", output_path, style_key, len(dialogue_lines))
    return os.path.abspath(output_path)

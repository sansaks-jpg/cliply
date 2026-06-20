"""Karaoke subtitle generator with pluggable animation styles (Strategy pattern).

Each style declares an ``animation`` key that dispatches to a builder function
in ``ANIMATION_BUILDERS``.  Adding a new style = adding a dict entry + a
builder — no if/elif chain to maintain.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
    return seg.get(key) or seg.get(key.replace("_time", ""))


def _split_words(text: str) -> List[str]:
    return text.strip().split()


def _apply_case(text: str, case: str) -> str:
    """Apply text casing from style config."""
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    return text


def _estimate_text_width(text: str, font_size: int) -> float:
    """Estimate rendered text width in pixels.

    Uses 0.55 × font_size per character (reasonable average for sans-serif).
    Not pixel-perfect — but good enough to enforce max_line_width_ratio
    without pulling in PIL/Pillow as a dependency.
    """
    char_width = font_size * 0.55
    return len(text) * char_width


def _wrap_text(
    text: str,
    style: Dict[str, Any],
    play_res_x: int,
    font_size: int,
) -> List[str]:
    """Wrap text into lines that fit within max_line_width_ratio.

    Returns a list of line strings (without ``\\N``).
    """
    max_ratio = style.get("max_line_width_ratio", 0.82)
    usable_width = play_res_x * max_ratio

    words = text.strip().split()
    if not words:
        return [""]

    lines: List[str] = []
    current = ""
    for w in words:
        candidate = f"{current} {w}".strip() if current else w
        if _estimate_text_width(candidate, font_size) > usable_width and current:
            lines.append(current)
            current = w
        else:
            current = candidate
    if current:
        lines.append(current)
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


# ── Animation builders ───────────────────────────────────────────
# Each returns a list[str] of Dialogue lines.


def build_karaoke_fill(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Karaoke fill — per-word colour highlight using \\kf tags.

    All words in one Dialogue line; libass auto-advances the fill.
    Long lines are wrapped via ``\\N`` to stay within max_line_width_ratio.
    """
    case = style.get("case", "normal")
    font_size = style.get("_font_size", 48)
    play_res_x = style.get("_play_res_x", 1080)
    lines: List[str] = []
    for seg in segments:
        t0 = _seg_time(seg, "start_time") or 0.0
        t1 = _seg_time(seg, "end_time") or 0.0
        text = (seg.get("text") or "").strip()
        if not text or t1 <= t0:
            continue
        wrapped = _wrap_text(_apply_case(text, case), style, play_res_x, font_size)
        words = _apply_case(text, case).split()
        if not words:
            continue
        total_cs = _cs(t1 - t0)
        per_word = max(1, total_cs // len(words))
        result_lines = []
        idx = 0
        for wline in wrapped:
            wcount = len(wline.split())
            chunk_words = words[idx:idx + wcount]
            idx += wcount
            parts = " ".join(f"{{\\kf{per_word}}}{w}" for w in chunk_words)
            result_lines.append(parts)
        lines.append(_dialogue(t0, t1, "\\N".join(result_lines), color=None))
    return lines


def build_karaoke_sweep(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Karaoke sweep — like fill but with outline flash on active word."""
    case = style.get("case", "normal")
    font_size = style.get("_font_size", 48)
    play_res_x = style.get("_play_res_x", 1080)
    lines: List[str] = []
    for seg in segments:
        t0 = _seg_time(seg, "start_time") or 0.0
        t1 = _seg_time(seg, "end_time") or 0.0
        text = (seg.get("text") or "").strip()
        if not text or t1 <= t0:
            continue
        wrapped = _wrap_text(_apply_case(text, case), style, play_res_x, font_size)
        words = _apply_case(text, case).split()
        if not words:
            continue
        total_cs = _cs(t1 - t0)
        per_word = max(1, total_cs // len(words))
        result_lines = []
        idx = 0
        for wline in wrapped:
            wcount = len(wline.split())
            chunk_words = words[idx:idx + wcount]
            idx += wcount
            parts = " ".join(f"{{\\kf{per_word}}}{w}" for w in chunk_words)
            result_lines.append(parts)
        lines.append(_dialogue(t0, t1, "\\N".join(result_lines), color=None))
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
    lines: List[str] = []
    for seg in segments:
        t0 = _seg_time(seg, "start_time") or 0.0
        t1 = _seg_time(seg, "end_time") or 0.0
        text = (seg.get("text") or "").strip()
        if not text or t1 <= t0:
            continue
        wrapped = _wrap_text(_apply_case(text, case), style, play_res_x, font_size)
        words = _apply_case(text, case).split()
        if not words:
            continue
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
                ms_offset = int(overall_idx * per_word * 1000)
                parts.append(
                    f"{{\\alpha&HFF&\\t({ms_offset},{ms_offset + fade_ms},\\alpha&H00&)}}{w}"
                )
            idx += wcount
            result_lines.append(" ".join(parts))
        
        lines.append(_dialogue(t0, t1, "\\N".join(result_lines), color=None))
    return lines


def build_word_popup(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Pop-up per word — each word scales in from small with a bounce.

    All words in one Dialogue line, avoiding overlapping center alignments.
    """
    pop_from = style.get("pop_scale_from", 70)
    pop_dur = style.get("pop_duration_ms", 200)
    case = style.get("case", "normal")
    font_size = style.get("_font_size", 48)
    play_res_x = style.get("_play_res_x", 1080)
    lines: List[str] = []
    for seg in segments:
        t0 = _seg_time(seg, "start_time") or 0.0
        t1 = _seg_time(seg, "end_time") or 0.0
        text = (seg.get("text") or "").strip()
        if not text or t1 <= t0:
            continue
        wrapped = _wrap_text(_apply_case(text, case), style, play_res_x, font_size)
        words = _apply_case(text, case).split()
        if not words:
            continue
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
                ms_offset = int(overall_idx * per_word * 1000)
                parts.append(
                    f"{{\\fscx{pop_from}\\fscy{pop_from}\\t({ms_offset},{ms_offset + pop_dur},\\fscx100\\fscy100)}}{w}"
                )
            idx += wcount
            result_lines.append(" ".join(parts))
            
        lines.append(_dialogue(t0, t1, "\\N".join(result_lines), color=None))
    return lines


def build_word_pop_scale(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Word pop scale — one word visible at a time, pops in from scale.

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
        if not text or t1 <= t0:
            continue
        words = _apply_case(text, case).split()
        if not words:
            continue
        duration = t1 - t0
        per_word = duration / len(words)
        for i, w in enumerate(words):
            ws = t0 + i * per_word
            we = t0 + (i + 1) * per_word
            lines.append(
                _dialogue(
                    ws, we,
                    f"{{\\fscx{pop_from}\\fscy{pop_from}\\t(0,{pop_dur},\\fscx100\\fscy100)}}{w}"
                )
            )
    return lines


def build_word_box_highlight(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Word box highlight — karaoke fill with thick border creating a box effect.

    Uses \\bord with very high value + \\kf to create a colored box that sweeps
    over each word as it's spoken.  ``box_border_width`` controls box thickness.
    Long lines are wrapped via ``\\N``.
    """
    box_color = style.get("box_color", "&H0076E600")
    border_w = style.get("box_border_width", 14)
    case = style.get("case", "normal")
    font_size = style.get("_font_size", 48)
    play_res_x = style.get("_play_res_x", 1080)
    lines: List[str] = []
    for seg in segments:
        t0 = _seg_time(seg, "start_time") or 0.0
        t1 = _seg_time(seg, "end_time") or 0.0
        text = (seg.get("text") or "").strip()
        if not text or t1 <= t0:
            continue
        wrapped = _wrap_text(_apply_case(text, case), style, play_res_x, font_size)
        words = _apply_case(text, case).split()
        if not words:
            continue
        total_cs = _cs(t1 - t0)
        per_word = max(1, total_cs // len(words))
        result_lines = []
        idx = 0
        for wline in wrapped:
            wcount = len(wline.split())
            chunk_words = words[idx:idx + wcount]
            idx += wcount
            parts = " ".join(f"{{\\kf{per_word}}}{w}" for w in chunk_words)
            result_lines.append(parts)
        joined = "\\N".join(result_lines)
        lines.append(
            f"Dialogue: 0,{_fmt(t0)},{_fmt(t1)},Default,,0,0,0,,"
            f"{{\\3c{box_color}}}{{\\bord{border_w}}}"
            f"{joined}"
        )
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
        "font": "Inter Black", "case": "upper",
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
        "font": "Inter", "case": "normal",
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
        "font": "Inter Black", "case": "normal",
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
        "font": "Arial", "case": "normal",
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
        "font": "Inter Black", "case": "upper",
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
        "font": "Inter", "case": "lower",
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00CCCCCC",
        "outline_color": "&H00000000", "outline_width": 0,
        "fade_ms": 150,
        "margin_v_ratio": 0.22, "margin_h_ratio": 0.09,
        "max_line_width_ratio": 0.82, "max_lines": 1,
        "font_size_ratio": 0.035, "bold": False,
    },
    "highlight-box": {
        "animation": "word_box_highlight",
        "font": "Inter Black", "case": "normal",
        "primary_color": "&H00FFFFFF",
        "box_color": "&H0076E600",
        "inactive_color": "&H00EEEEEE",
        "box_border_width": 14,
        "outline_color": "&H00000000", "outline_width": 0,
        "margin_v_ratio": 0.26, "margin_h_ratio": 0.09,
        "max_line_width_ratio": 0.82, "max_lines": 2,
        "font_size_ratio": 0.042, "bold": True,
    },
    "neon-gradient": {
        "animation": "karaoke_fill",
        "font": "Inter Black", "case": "upper",
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
        "font": "Inter Black", "case": "upper",
        "primary_color": "&H00FFFFFF",
        "highlight_color": "&H0008E539",
        "outline_color": "&H00000000",
        "outline_width": 20, "blur": 0,
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
    blur = style.get("blur", 0)

    # Shadow field doubles as blur in ASS (Shadow=blur when BorderStyle=1)
    shadow = blur if blur else 0

    anim = style.get("animation", "karaoke_fill")
    if anim in ("karaoke_fill", "karaoke_sweep", "word_box_highlight"):
        # Sweep changes text color from Secondary (before pronunciation) to Primary (after pronunciation).
        # Inactive color = Secondary color = primary_color (usually white).
        # Active color = Primary color = highlight_color (usually yellow).
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
        f"{style['outline_color']},{_BLACK},"
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
        if not text or t1 <= t0:
            continue
            
        words = text.split()
        if not words:
            continue
            
        n_words = len(words)
        duration = t1 - t0
        per_word = duration / n_words
        
        for i in range(0, n_words, chunk_size):
            chunk_words = words[i:i + chunk_size]
            c_start = t0 + i * per_word
            c_end = t0 + min(n_words, i + chunk_size) * per_word
            
            new_seg = dict(seg)
            new_seg["start"] = c_start
            new_seg["end"] = c_end
            new_seg["start_time"] = c_start
            new_seg["end_time"] = c_end
            new_seg["text"] = " ".join(chunk_words)
            chunked.append(new_seg)
            
    return chunked


def generate_ass(
    segments: List[Dict[str, Any]],
    style_key: str,
    output_path: str,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    fonts_dir: Optional[str] = None,
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

    Returns:
        The absolute path of the generated file.
    """
    if style_key not in STYLES:
        log.warning("Unknown subtitle style %r, falling back to %r", style_key, DEFAULT_STYLE)
        style_key = DEFAULT_STYLE

    style = STYLES[style_key]
    font_size = max(20, int(play_res_y * style["font_size_ratio"]))
    style = {**style, "_font_size": font_size, "_play_res_x": play_res_x}
    
    # Split segments into optimal chunks before building dialogue lines
    chunked_segments = _chunk_segments(segments, style)
    
    builder = ANIMATION_BUILDERS[style["animation"]]
    dialogue_lines = builder(chunked_segments, style)
    header = _header(style, play_res_x, play_res_y)
    content = header + "\n".join(dialogue_lines) + "\n"

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write(content)

    log.info("Generated ASS subtitle: %s (style=%s, %d lines)", output_path, style_key, len(dialogue_lines))
    return os.path.abspath(output_path)

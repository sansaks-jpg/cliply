"""Subtitle animation builders — each returns a list[str] of ASS Dialogue lines.

Builders implement different visual effects for karaoke-style subtitles:
- karaoke_fill: per-word instant colour pop
- karaoke_sweep: dual-layer glow with static blur
- fade_in_word: per-word alpha fade
- word_popup: per-word scale pop with ease-out
- word_pop_scale: one word visible at a time
- word_box_highlight: inline color highlight on active word
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

log = logging.getLogger(__name__)

# ── ASS colours (decimal &HBBGGRR) ───────────────────────────────
_WHITE = "&H00FFFFFF"
_YELLOW = "&H0000FFFF"
_BLACK = "&H00000000"
_CYAN = "&H00FFFF00"
_MAGENTA = "&H00FF00FF"


# ── Text helpers (duplicated from subtitles.py to avoid circular import) ──

def _clean_text(text: str) -> str:
    """Remove punctuation, keep only words and spaces."""
    import re
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


def _seg_time(seg: Dict[str, Any], key: str) -> float | None:
    """Read a timestamp from a segment, supporting both naming conventions."""
    val = seg.get(key)
    if val is not None:
        return float(val)
    val = seg.get(key.replace("_time", ""))
    if val is not None:
        return float(val)
    return None


def _cs(seconds: float) -> int:
    """Convert seconds to centiseconds (ASS \\k units)."""
    return max(0, int(seconds * 100))


def _fmt(seconds: float | None) -> str:
    """Seconds → ``H:MM:SS.cc`` (ASS timestamp)."""
    s = max(0.0, seconds or 0.0)
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    cs = int((s % 1) * 100)
    return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"


def _dialogue(
    start: float,
    end: float,
    text: str,
    color: str | None = None,
    effect: str = "",
) -> str:
    colour_tag = f"{{\\c{color}}}" if color else ""
    effect_tag = f"{{\\{effect}}}" if effect else ""
    return (
        f"Dialogue: 0,{_fmt(start)},{_fmt(end)},Default,,0,0,0,,"
        f"{colour_tag}{effect_tag}{text}"
    )


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


def _find_adaptive_wrap(
    text: str,
    style: Dict[str, Any],
    play_res_x: int,
    base_font_size: int,
) -> tuple[List[str], int]:
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


def _blur_prefix(style: Dict[str, Any]) -> str:
    """Return an inline \\blur<n> tag if the style has blur > 0, else empty string."""
    blur = style.get("blur", 0)
    return f"{{\\blur{blur}}}" if blur else ""


def _build_karaoke_base(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
    tag_prefix: str = "\\kf",
) -> List[str]:
    """Helper to build standard karaoke-style ASS lines."""
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
        cased_text = _apply_case(text, case)
        wrapped, adaptive_fs = _find_adaptive_wrap(cased_text, style, play_res_x, font_size)
        words = cased_text.split()
        if not words:
            continue
        total_cs = _cs(t1 - t0)

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
        if adaptive_fs != font_size:
            diag_text = f"{{\\fs{adaptive_fs}}}" + diag_text
        if blur_tag:
            diag_text = blur_tag + diag_text
        lines.append(_dialogue(t0, t1, diag_text, color=None))
    return lines


def build_karaoke_fill(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Karaoke fill — per-word instant colour pop using \\k."""
    return _build_karaoke_base(segments, style, "\\k")


def build_karaoke_sweep(
    segments: List[Dict[str, Any]],
    style: Dict[str, Any],
) -> List[str]:
    """Karaoke sweep — dual-layer static blur glow for maximum CPU performance."""
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

        cased_text = _apply_case(text, case)
        wrapped, adaptive_fs = _find_adaptive_wrap(cased_text, style, play_res_x, font_size)
        words = cased_text.split()
        if not words:
            continue

        total_cs = _cs(t1 - t0)
        flash_dur = min(20, (total_cs * 10) // (len(words) * 2))

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

        # LAYER 0: GLOW BACKGROUND
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

        # LAYER 1: SHARP FOREGROUND
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
    """Fade-in per word — each word appears with a short alpha transition."""
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
        cased_text = _apply_case(text, case)
        wrapped, adaptive_fs = _find_adaptive_wrap(cased_text, style, play_res_x, font_size)
        words = cased_text.split()
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
    """Pop-up per word — each word scales in from small with a descelerated bounce (ease-out)."""
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
        cased_text = _apply_case(text, case)
        wrapped, adaptive_fs = _find_adaptive_wrap(cased_text, style, play_res_x, font_size)
        words = cased_text.split()
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
    """Word pop scale — one word visible at a time, pops in from scale with desceleration (ease-out)."""
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
        cased_text = _apply_case(text, case)
        words = cased_text.split()
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
    """Word box highlight — inline color tags to highlight the active word."""
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

        cased_text = _apply_case(text, case)
        wrapped, adaptive_fs = _find_adaptive_wrap(cased_text, style, play_res_x, font_size)
        words = cased_text.split()
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

            if i == 0 and ws > t0:
                words_all_inactive = []
                for wline in wrapped:
                    words_all_inactive.append(wline)
                inactive_text = f"{{\\1c{inactive_color}}}" + "\\N".join(words_all_inactive)
                if adaptive_fs != font_size:
                    inactive_text = f"{{\\fs{adaptive_fs}}}" + inactive_text
                lines.insert(0, _dialogue(t0, ws, inactive_text, color=None))

            if i == len(words) - 1 and we < t1:
                words_all_inactive = []
                for wline in wrapped:
                    words_all_inactive.append(wline)
                inactive_text = f"{{\\1c{inactive_color}}}" + "\\N".join(words_all_inactive)
                if adaptive_fs != font_size:
                    inactive_text = f"{{\\fs{adaptive_fs}}}" + inactive_text
                lines.append(_dialogue(we, t1, inactive_text, color=None))
    return lines

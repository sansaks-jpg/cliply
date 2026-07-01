"""Subtitle style definitions and animation builder registry.

Each style declares an ``animation`` key that dispatches to a builder function
in ``ANIMATION_BUILDERS``.  Adding a new style = adding a dict entry + a
builder — no if/elif chain to maintain.
"""
from __future__ import annotations

from typing import Any, Callable, Dict

# ── ASS colours (decimal &HBBGGRR) ───────────────────────────────
_WHITE = "&H00FFFFFF"
_YELLOW = "&H0000FFFF"
_RED = "&H000000FF"
_BLACK = "&H00000000"
_GRAY = "&H00999999"
_CYAN = "&H00FFFF00"
_MAGENTA = "&H00FF00FF"
_DARK_GRAY = "&H00444444"


# ── Animation builder imports (lazy to avoid circular) ────────────
def _get_builders() -> Dict[str, Callable]:
    from .subtitle_builders import (
        build_karaoke_fill,
        build_karaoke_sweep,
        build_fade_in_word,
        build_word_popup,
        build_word_pop_scale,
        build_word_box_highlight,
    )
    return {
        "karaoke_fill": build_karaoke_fill,
        "karaoke_sweep": build_karaoke_sweep,
        "fade_in_word": build_fade_in_word,
        "word_popup": build_word_popup,
        "word_pop_scale": build_word_pop_scale,
        "word_box_highlight": build_word_box_highlight,
    }


# ── Style registry ────────────────────────────────────────────────

STYLES: Dict[str, Dict[str, Any]] = {
    # ── Original styles (kept) ────────────────────────────────────
    "viral-bold": {
        "animation": "karaoke_fill",
        "font": "Plus Jakarta Sans", "case": "upper",
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
        "font": "Plus Jakarta Sans", "case": "normal",
        "font_size_ratio": 0.035,
        "primary_color": _WHITE,
        "outline_color": _DARK_GRAY,
        "outline_width": 1,
        "margin_v_ratio": 0.22, "margin_h_ratio": 0.09,
        "max_line_width_ratio": 0.82,
        "bold": False,
        "fade_ms": 150,
    },
    "classic-popup": {
        "animation": "word_popup",
        "font": "Plus Jakarta Sans", "case": "normal",
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
        "font": "Plus Jakarta Sans", "case": "lower",
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
